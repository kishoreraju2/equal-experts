# GitHub Gists Server - Docker Deployment

## Best Practices Implemented

### Security
- ✅ **Non-root user**: Runs as `equalexperts` with minimal privileges
- ✅ **Read-only filesystem**: Container filesystem is immutable
- ✅ **No new privileges**: Prevents privilege escalation
- ✅ **Dropped capabilities**: All Linux capabilities removed
- ✅ **Specific base image**: Uses versioned Python image (not `latest`)

### Performance & Reliability
- ✅ **Healthcheck**: Automatic container health monitoring
- ✅ **Restart policy**: Auto-restart on failure
- ✅ **Unbuffered Python**: Immediate log output
- ✅ **.dockerignore**: Faster builds, smaller context

### Operations
- ✅ **Environment variables**: Configurable port

## Quick Start

### Using Docker CLI
```bash
# Build image
docker build -t github-gists-server:latest .

# Run container
docker run -d \
  --name gists-api \
  -p 8080:8080 \
  --read-only \
  --security-opt no-new-privileges:true \
  --cap-drop ALL \
  --restart unless-stopped \
  github-gists-server:latest

# Check health
docker ps
docker inspect gists-api | grep -A 5 Health

# View logs
docker logs -f gists-api

# Stop and remove
docker stop gists-api
docker rm gists-api
```

## Testing

```bash
# Test the API
curl http://localhost:8080/octocat

# Check health endpoint
curl http://localhost:8080/

# Test error handling
curl http://localhost:8080/nonexistentuser123456
```


### Permission issues
The container runs as non-root user `equalexperts`. Ensure mounted volumes have correct permissions.

