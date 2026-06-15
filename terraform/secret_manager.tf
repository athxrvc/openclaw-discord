resource "google_secret_manager_secret" "discord_token" {
  secret_id = "discord-token"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "database-url"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "ollama_url" {
  secret_id = "ollama-url"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "default_model" {
  secret_id = "default-model"

  replication {
    auto {}
  }
}