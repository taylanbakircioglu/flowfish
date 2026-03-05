# Flowfish Frontend Dockerfile
# Build context should be workspace root

# Build stage
FROM node:18-alpine AS builder

# Cache bust - increment to force fresh build
ARG CACHE_BUST=20260130v2
RUN echo "Build: $CACHE_BUST"

WORKDIR /app

# Copy package files from frontend directory
COPY frontend/package*.json ./

# Fix EMFILE "too many open files" - all in one layer with env vars
ENV npm_config_cache=/tmp/npm-cache
ENV npm_config_maxsockets=1
ENV npm_config_fetch_retries=3
ENV npm_config_loglevel=warn

# Install dependencies with aggressive cleanup
RUN rm -rf /root/.npm /tmp/* node_modules && \
    mkdir -p /tmp/npm-cache && \
    npm install --legacy-peer-deps --no-audit --no-fund --prefer-offline 2>&1 || \
    (echo "Retry with clean cache..." && rm -rf /tmp/npm-cache && mkdir -p /tmp/npm-cache && npm install --legacy-peer-deps --no-audit --no-fund)

# Copy source code from frontend directory
COPY frontend/ .

# Build production bundle with increased memory
ENV NODE_OPTIONS="--max-old-space-size=4096"
RUN npm run build

# Production stage
FROM nginx:alpine AS production

# Remove default nginx website
RUN rm -rf /usr/share/nginx/html/*

# Copy built app
COPY --from=builder /app/build /usr/share/nginx/html

# Copy nginx configuration from frontend directory
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# OpenShift compatibility: Set permissions for arbitrary UID
RUN chown -R nginx:0 /usr/share/nginx/html && \
    chmod -R g=u /usr/share/nginx/html && \
    chown -R nginx:0 /var/cache/nginx && \
    chmod -R g=u /var/cache/nginx && \
    chown -R nginx:0 /var/run && \
    chmod -R g=u /var/run

# Switch to non-root user  
USER nginx

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
