locals {
  docs_bucket_name   = var.docs_bucket_suffix != "" ? "${local.name_prefix}-docs-${var.docs_bucket_suffix}" : "${local.name_prefix}-docs-${local.account_id}"
  images_bucket_name = var.images_bucket_suffix != "" ? "${local.name_prefix}-images-${var.images_bucket_suffix}" : "${local.name_prefix}-images-${local.account_id}"
}

# ─────────────────────────────────────────────────────────────
# S3: Company Documents (source for Knowledge Base)
# ─────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "docs" {
  bucket        = local.docs_bucket_name
  force_destroy = false

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_s3_bucket_versioning" "docs" {
  bucket = aws_s3_bucket.docs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "docs" {
  bucket = aws_s3_bucket.docs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "docs" {
  bucket                  = aws_s3_bucket.docs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Placeholder prefixes — upload your documents here
resource "aws_s3_object" "docs_prefix_reports" {
  bucket  = aws_s3_bucket.docs.id
  key     = "reports/"
  content = ""
}

resource "aws_s3_object" "docs_prefix_policies" {
  bucket  = aws_s3_bucket.docs.id
  key     = "policies/"
  content = ""
}


# ─────────────────────────────────────────────────────────────
# S3: Generated Images
# ─────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "images" {
  bucket        = local.images_bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "images" {
  bucket = aws_s3_bucket.images.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "images" {
  bucket                  = aws_s3_bucket.images.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Auto-delete generated images after 7 days
resource "aws_s3_bucket_lifecycle_configuration" "images" {
  bucket = aws_s3_bucket.images.id

  rule {
    id     = "expire-generated-images"
    status = "Enabled"
    filter {
      prefix = "generated/"
    }
    expiration {
      days = 7
    }
  }
}
