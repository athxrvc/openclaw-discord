resource "google_sql_database_instance" "postgres" {
  name             = "openclaw-postgres"
  database_version = "POSTGRES_16"
  region           = var.region

settings {
  activation_policy = "ALWAYS"
  availability_type = "ZONAL"
  disk_autoresize = true

  tier = "db-f1-micro"
  edition = "ENTERPRISE"
}

  deletion_protection = true
}

resource "google_sql_database" "openclaw" {
  name     = "openclaw"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "openclaw" {
  name     = "openclaw_user"
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}