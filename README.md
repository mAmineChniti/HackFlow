# HackFlow

Django 5.2 project with MySQL, Docker Compose, and Render Blueprint.

## Quickstart (Docker + MySQL)

```bash
cp .env.example .env
docker compose up --build
```

- App: http://localhost:8000
- Admin: http://localhost:8000/admin/
- Health: http://localhost:8000/health/
- MySQL: localhost:3306 (`hackflow` / `hackflow` / `hackflow`)

Migrations + collectstatic run automatically via `docker-entrypoint.sh`.

## Local (no Docker, MySQL 8 required)

Need MySQL 8 running + `mysqlclient` system libs, then:

```bash
pip install -r requirements.txt
export MYSQL_DATABASE=hackflow MYSQL_USER=hackflow MYSQL_PASSWORD=hackflow MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306
python manage.py migrate
python manage.py runserver
```

## Deploy to Render

1. Push this repo to GitHub.
2. Render Dashboard → New → Blueprint → select repo (`render.yaml` auto-detected).
3. Approve:
   - `hackflow` (web, Docker, `/health/`)
   - `hackflow-mysql` (private, `mysql:8.0` + 10GB disk)
4. Web gets `MYSQL_*` wired from the MySQL private service automatically.

Alternatively set `DATABASE_URL=mysql://user:pass@host:3306/hackflow` if using external MySQL (Aiven/PlanetScale/RDS).
