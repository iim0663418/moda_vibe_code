FROM node:20-alpine

WORKDIR /app

RUN npm install -g npm@latest
RUN apk add --no-cache wget

# Create health check script
RUN echo '#!/bin/sh \n\
# Simple health check that verifies the process is running \n\
if pgrep -f "server-github" > /dev/null; then \n\
  exit 0 \n\
else \n\
  exit 1 \n\
fi' > /app/health-check.sh && chmod +x /app/health-check.sh

# Create startup script that includes a simple HTTP server for health checks
RUN printf '#!/bin/sh\n\
echo "Starting health check server..."\n\
(while true; do\n\
  printf "HTTP/1.1 200 OK\\r\\nContent-Length: 42\\r\\n\\r\\n{\\"status\\":\\"healthy\\",\\"service\\":\\"mcp-github\\"}" | nc -l -p 8080\n\
done) &\n\
\n\
echo "Starting GitHub MCP server..."\n\
exec npx -y @modelcontextprotocol/server-github\n' > /app/start.sh && chmod +x /app/start.sh

EXPOSE 3000 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8080/ || exit 1

CMD ["/app/start.sh"]
