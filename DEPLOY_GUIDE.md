# DigitalOcean Deployment Guide

This guide will walk you through deploying the FIND-MISSING-PEP project to a DigitalOcean Droplet using Docker Compose.

## 1. Create a DigitalOcean Droplet
1. Log in to your DigitalOcean account.
2. Click **Create** > **Droplets**.
3. Choose **Region**: Select a region closest to your target users.
4. Choose **Image**: Select the **Marketplace** tab, search for **Docker**, and select the **Docker** image on Ubuntu.
5. Choose **Size**: Select a size with at least **2GB RAM** (4GB recommended for AI models and Postgres).
6. Choose **Authentication Method**: SSH Key (Recommended) or Password.
7. Click **Create Droplet**.

## 2. Access Your Droplet
Once the Droplet is ready, copy its IPv4 address.
SSH into your server:
```bash
ssh root@YOUR_DROPLET_IP
```

## 3. Clone the Project
Inside your droplet, clone your repository (you may need to set up a GitHub deploy key or use HTTPS with a Personal Access Token):

```bash
git clone https://github.com/yourusername/find-missing-pep.git
cd find-missing-pep
```

## 4. Setup Environment Variables
Copy the production environment example file and configure it:

```bash
cp .env.prod.example .env
nano .env
```
Update `POSTGRES_PASSWORD`, `ADMIN_ENROLLMENT_KEY`, and `RTSP_SECRET_KEY` with strong random values. Save and exit (`Ctrl+X`, then `Y`, then `Enter`).

> **Important Note for Firebase**: If you are using Firebase Auth, you need to open `web_app/.env.production` and fill in your Firebase API keys before the next step, as they are baked into the frontend during the Docker build process.
> ```bash
> nano web_app/.env.production
> ```

## 5. Start the Application
Run Docker Compose in detached mode using the production configuration:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

This will:
- Start PostgreSQL and Redis databases.
- Build and start the FastAPI Backend (it will run migrations automatically).
- Build the React Frontend (Vite) and start an Nginx server to serve it on Port 80.

## 6. Access the Application
Open your browser and navigate to: `http://YOUR_DROPLET_IP`

## 7. Next Steps: Setting up HTTPS (Optional but Recommended)
If you want to secure your application with HTTPS (required for accessing Webcams from mobile browsers), the easiest way is:
1. Purchase a domain name and point an `A Record` to your Droplet IP.
2. Use **Cloudflare** (Free tier) to proxy your traffic. Cloudflare will automatically provide HTTPS encryption between your users and Cloudflare, while talking HTTP to your Droplet on port 80.
3. Alternatively, you can install **Caddy** on your droplet as a reverse proxy, which automatically provisions Let's Encrypt certificates.
