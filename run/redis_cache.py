"""
Redis cache helper for CaseLinker API
Provides fast, shared caching for static visualization endpoints
"""
import json
import os
import sys
import redis
from typing import Any, Optional
from functools import wraps

# Redis connection - supports both local and cloud (Railway, Render, etc.)
# Railway automatically provides REDIS_URL when Redis service is added
# Format: redis://default:password@host:port
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', None)

# Railway-specific: Check for Railway Redis environment variables
# Railway may provide REDIS_URL with embedded password
if not REDIS_PASSWORD and REDIS_URL and '@' in REDIS_URL:
    # Extract password from URL if present (Railway format)
    try:
        from urllib.parse import urlparse
        parsed = urlparse(REDIS_URL)
        if parsed.password:
            REDIS_PASSWORD = parsed.password
    except:
        pass

# Initialize Redis client with connection pooling
try:
    # Connection settings optimized for production
    connection_kwargs = {
        'decode_responses': True,
        'socket_connect_timeout': 5,
        'socket_timeout': 5,
        'retry_on_timeout': True,
        'health_check_interval': 30,  # Check connection health every 30s
        'socket_keepalive': True,
        'socket_keepalive_options': {}
    }
    
    if REDIS_PASSWORD:
        redis_client = redis.from_url(
            REDIS_URL,
            password=REDIS_PASSWORD,
            **connection_kwargs
        )
    else:
        redis_client = redis.from_url(
            REDIS_URL,
            **connection_kwargs
        )
    
    # Test connection with timeout
    redis_client.ping()
    REDIS_AVAILABLE = True
    
    # Log connection info (without sensitive data)
    redis_host = REDIS_URL.split('@')[-1] if '@' in REDIS_URL else REDIS_URL.split('://')[-1]
    print(f"✅ Redis cache connected successfully ({redis_host})", file=sys.stderr)
except Exception as e:
    print(f"⚠️  Redis not available: {e}", file=sys.stderr)
    print("   Falling back to direct database queries (slower)", file=sys.stderr)
    print("   To enable caching: Add Redis service in Railway or set REDIS_URL environment variable", file=sys.stderr)
    REDIS_AVAILABLE = False
    redis_client = None


def get_case_count(storage_instance=None) -> int:
    """Get current case count from database (fast query for cache invalidation)"""
    try:
        if storage_instance:
            # Use provided storage instance
            import sqlite3
            db_conn = sqlite3.connect(storage_instance.db_path)
            cursor = db_conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM cases')
            count = cursor.fetchone()[0]
            db_conn.close()
            return count
        else:
            # Fallback: create storage instance
            from storage import CaseStorage
            from config import DATABASE_PATH
            from pathlib import Path
            
            # Determine database path
            if Path(__file__).parent.name == 'run':
                db_path = Path(__file__).parent.parent / DATABASE_PATH
            else:
                db_path = Path(DATABASE_PATH)
            
            storage = CaseStorage(str(db_path))
            import sqlite3
            db_conn = sqlite3.connect(storage.db_path)
            cursor = db_conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM cases')
            count = cursor.fetchone()[0]
            db_conn.close()
            return count
    except Exception as e:
        print(f"⚠️  Error getting case count: {e}", file=sys.stderr)
        return 0


def get_cache_key(endpoint: str, **kwargs) -> str:
    """Generate cache key from endpoint and parameters"""
    # Sort kwargs for consistent keys
    params = '_'.join(f"{k}:{v}" for k, v in sorted(kwargs.items()))
    if params:
        return f"caselinker:{endpoint}:{params}"
    return f"caselinker:{endpoint}"


def get_cached(key: str) -> Optional[Any]:
    """Get value from Redis cache"""
    if not REDIS_AVAILABLE or not redis_client:
        return None
    
    try:
        cached = redis_client.get(key)
        if cached:
            # Try faster JSON parsing if available, fallback to standard json
            try:
                import orjson
                return orjson.loads(cached)
            except ImportError:
                return json.loads(cached)
    except redis.ConnectionError as e:
        # Connection lost - mark as unavailable for this request
        print(f"⚠️  Redis connection lost: {e}", file=sys.stderr)
        return None
    except Exception as e:
        # Other errors - log but don't crash
        print(f"⚠️  Redis get error: {e}", file=sys.stderr)
    return None


def set_cached(key: str, value: Any, ttl: int = 3600) -> bool:
    """Set value in Redis cache with TTL (default 1 hour)"""
    if not REDIS_AVAILABLE or not redis_client:
        return False
    
    try:
        # Try faster JSON serialization if available, fallback to standard json
        try:
            import orjson
            serialized = orjson.dumps(value).decode('utf-8')
        except ImportError:
            serialized = json.dumps(value)
        redis_client.setex(key, ttl, serialized)
        return True
    except redis.ConnectionError as e:
        # Connection lost - mark as unavailable
        print(f"⚠️  Redis connection lost: {e}", file=sys.stderr)
        return False
    except Exception as e:
        # Other errors - log but don't crash
        print(f"⚠️  Redis set error: {e}", file=sys.stderr)
    return False


def invalidate_cache_pattern(pattern: str) -> int:
    """Invalidate all cache keys matching pattern"""
    if not REDIS_AVAILABLE or not redis_client:
        return 0
    
    try:
        keys = redis_client.keys(pattern)
        if keys:
            return redis_client.delete(*keys)
        return 0
    except Exception as e:
        print(f"⚠️  Redis invalidation error: {e}", file=sys.stderr)
    return 0


def cache_with_version(endpoint: str, version_key: str, ttl: int = 3600):
    """
    Decorator for caching API responses with version-based invalidation.
    
    Args:
        endpoint: Endpoint name for cache key
        version_key: Key to check for version (e.g., 'case_count')
        ttl: Time to live in seconds (default 1 hour)
    
    Usage:
        @cache_with_version('cases', 'case_count')
        def get_cases(include_raw_data=False):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get current version (e.g., case count)
            if version_key == 'case_count':
                current_version = get_case_count()
            else:
                current_version = kwargs.get(version_key, 'default')
            
            # Build cache key with version
            cache_key = get_cache_key(endpoint, version=current_version, **kwargs)
            
            # Try cache first
            cached_result = get_cached(cache_key)
            if cached_result is not None:
                # Add cache indicator
                if isinstance(cached_result, dict):
                    cached_result['_cached'] = True
                    cached_result['_cache_source'] = 'redis'
                return cached_result
            
            # Cache miss - compute result
            result = func(*args, **kwargs)
            
            # Store in cache
            set_cached(cache_key, result, ttl)
            
            # Add cache indicator
            if isinstance(result, dict):
                result['_cached'] = False
                result['_cache_source'] = 'database'
            
            return result
        return wrapper
    return decorator


def clear_all_cache():
    """Clear all CaseLinker cache entries (useful for testing/debugging)"""
    if not REDIS_AVAILABLE or not redis_client:
        return 0
    return invalidate_cache_pattern('caselinker:*')
