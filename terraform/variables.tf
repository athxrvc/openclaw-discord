variable "project_id" {
  type = string
  default = "openclaw-bot-1971"
}

variable "region" {
  type = string
  default = "europe-west1"
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "Password for the Cloud SQL postgres user"
}