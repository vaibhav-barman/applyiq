#!/bin/sh
# Runs once, when the Postgres data volume is first created (docker-entrypoint-initdb.d).
# Creates the role the app, Alembic and the tests connect as. POSTGRES_USER stays the
# bootstrap superuser for the healthcheck and manual admin only.
#
# NOSUPERUSER: an injection or a bug in the app cannot use COPY ... PROGRAM or read
# server files. CREATEDB is for the *_test databases in local development only; the
# production role must not have it. psql quotes the name and password itself
# (:"app_user", :'app_password'), so neither is spliced into the SQL text.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_user="$APP_DB_USER" -v app_password="$APP_DB_PASSWORD" -v app_db="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"app_user" LOGIN NOSUPERUSER NOCREATEROLE NOREPLICATION CREATEDB
  PASSWORD :'app_password';
ALTER DATABASE :"app_db" OWNER TO :"app_user";
ALTER SCHEMA public OWNER TO :"app_user";
SQL
