docker rm -f flaresolverr 2>/dev/null || true
docker run -d \
    --name=flaresolverr \
    -p 8191:8191 \
    -e LOG_LEVEL=info \
    -e BROWSER_PROXY_SERVER=http://host.docker.internal:7077 \
    --restart unless-stopped \
    ghcr.io/flaresolverr/flaresolverr:latest
