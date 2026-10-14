# Campus Nexus — Production Deployment & DevOps Runbook

---

## 1. System Requirements & Stack Specifications

| Component | Minimum Specification | Production Recommended |
| :--- | :--- | :--- |
| **Operating System** | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| **Compute / Memory** | 2 vCPU, 2 GB RAM | 4 vCPU, 8 GB RAM (Multi-core ASGI) |
| **Relational Database**| PostgreSQL 15 | PostgreSQL 16+ with PgBouncer |
| **Cache & Channels** | Redis 6 | Redis 7+ Cluster (AOF enabled) |
| **Application Server** | Daphne 4.x (1 worker) | Daphne / Uvicorn (4 worker processes) |
| **Reverse Proxy** | Nginx 1.22+ | Nginx 1.26+ (HTTP/2, TLS 1.3, Brotli) |

---

## 2. Environment Variables Configuration (`.env`)

Deploy with a hardened production `.env` file:

```ini
# Core
DJANGO_SECRET_KEY=generate-a-cryptographically-secure-random-64-char-key
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=nexus.nitsri.ac.in,www.nexus.nitsri.ac.in

# Database (PostgreSQL)
DATABASE_URL=postgres://nexus_admin:UltraSecurePass123@127.0.0.1:5432/campus_nexus_db

# Cache & Channels (Redis)
REDIS_URL=redis://127.0.0.1:6379/0

# Production Email (Google Workspace or Amazon SES)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=noreply.campus.nexus@gmail.com
EMAIL_HOST_PASSWORD=your-16-char-app-password
DEFAULT_FROM_EMAIL=Campus Nexus <noreply.campus.nexus@gmail.com>

# Security Hardening
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
DJANGO_SECURE_HSTS_SECONDS=31536000
```

---

## 3. Systemd Service Configuration

Create `/etc/systemd/system/campus-nexus.service`:

```ini
[Unit]
Description=Campus Nexus Daphne ASGI Application Server
After=network.target redis.service postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/campus_nexus
EnvironmentFile=/var/www/campus_nexus/.env
ExecStart=/var/www/campus_nexus/venv/bin/daphne \
    -b 127.0.0.1 \
    -p 8000 \
    --access-log /var/log/campus_nexus/access.log \
    campus.asgi:application

Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now campus-nexus.service
```

---

## 4. Nginx Reverse Proxy & SSL Configuration

Create `/etc/nginx/sites-available/campus_nexus`:

```nginx
upstream campus_nexus_asgi {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name nexus.nitsri.ac.in;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name nexus.nitsri.ac.in;

    ssl_certificate /etc/letsencrypt/live/nexus.nitsri.ac.in/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nexus.nitsri.ac.in/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 10M;

    # Static Assets with 30-Day Browser Caching
    location /static/ {
        alias /var/www/campus_nexus/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # Uploaded Profile Media
    location /media/ {
        alias /var/www/campus_nexus/media/;
        expires 7d;
        add_header Cache-Control "private, no-transform";
    }

    # WebSocket Real-Time Traffic
    location /ws/ {
        proxy_pass http://campus_nexus_asgi;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # HTTP Application Routing
    location / {
        proxy_pass http://campus_nexus_asgi;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/campus_nexus /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 5. Telecom DLT SMS Gateway Integration

To enable production carrier SMS dispatch alongside the active email OTP engine:
1. **TRAI DLT Portal:** Register entity at [Vilpower](https://www.vilpower.in/) or [Jio DLT](https://trueconnect.jio.com/).
2. **Approved Header:** Register sender header `NITSRI`.
3. **Approved Template:**
   ```text
   Your Campus Nexus verification code is {#var#}. Valid for 5 minutes. National Institute of Technology Srinagar.
   ```
4. **Driver Plugin:** In `accounts/two_factor.py`, update `dispatch_sms_otp()` to call your chosen provider's HTTP REST API (Twilio, AWS SNS, MSG91, or Fast2SMS) using the approved template ID.
