variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-2"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.medium"
}

variable "key_name" {
  description = "AWS key pair name"
  type        = string
}

variable "docker_compose_file" {
  description = "Docker compose file path"
  type        = string
  default     = "docker-compose.yml"
}

