#!/bin/bash
# ============================================
# BizOS Secret Generation Script
# ============================================
# Generates all required cryptographic keys and secrets
# for BizOS deployment
#
# Usage:
#   ./generate-secrets.sh
#
# Output:
#   .env.generated - File containing all generated secrets
#
# WARNING: Keep .env.generated secure and delete after use
# ============================================

set -e  # Exit on error

echo "🔐 BizOS Secret Generation Script"
echo "=================================="
echo ""

# Check prerequisites
command -v openssl >/dev/null 2>&1 || { echo "❌ Error: openssl is required but not installed."; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ Error: node is required but not installed."; exit 1; }

echo "✓ Prerequisites check passed"
echo ""

# Generate encryption keys (64-char hex = 32 bytes)
echo "Generating encryption keys..."
DB_ENCRYPTION_KEY=$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")
SQLITE_MASTER_KEY=$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")
CHANNEL_ENCRYPTION_KEY=$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")
CSRF_SECRET=$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")
API_INTERNAL_KEY=$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")
echo "✓ Encryption keys generated"

# Generate Redis password
echo "Generating Redis password..."
REDIS_PASSWORD=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)
echo "✓ Redis password generated"

# Generate JWT RSA-4096 keypair
echo "Generating JWT RSA-4096 keypair..."
openssl genrsa -out private.pem 4096 2>/dev/null
openssl rsa -in private.pem -pubout -out public.pem 2>/dev/null
RS_PRIVATE_KEY=$(base64 < private.pem | tr -d '\n')
RS_PUBLIC_KEY=$(base64 < public.pem | tr -d '\n')
rm private.pem public.pem
echo "✓ JWT keypair generated"

# Generate Admin JWT RSA-4096 keypair
echo "Generating Admin JWT RSA-4096 keypair..."
openssl genrsa -out admin_private.pem 4096 2>/dev/null
openssl rsa -in admin_private.pem -pubout -out admin_public.pem 2>/dev/null
ADMIN_RS_PRIVATE_KEY=$(base64 < admin_private.pem | tr -d '\n')
ADMIN_RS_PUBLIC_KEY=$(base64 < admin_public.pem | tr -d '\n')
rm admin_private.pem admin_public.pem
echo "✓ Admin JWT keypair generated"

# Generate verification tokens
echo "Generating webhook verification tokens..."
WHATSAPP_VERIFY_TOKEN=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)
FACEBOOK_WEBHOOK_VERIFY_TOKEN=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)
WHATSAPP_WEBHOOK_SECRET=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)
echo "✓ Verification tokens generated"

# Write to file
OUTPUT_FILE=".env.generated"
cat > "$OUTPUT_FILE" << EOF
# ============================================
# BizOS Generated Secrets
# ============================================
# Generated: $(date '+%Y-%m-%d %H:%M:%S')
#
# SECURITY INSTRUCTIONS:
# 1. Copy these values to your .env file
# 2. DELETE this file after copying: rm .env.generated
# 3. NEVER commit this file to version control
# 4. Store securely (password manager, secrets management system)
# ============================================

# ============================================
# ENCRYPTION KEYS (AES-256-GCM)
# ============================================
# Database field encryption (MFA secrets, passwords)
DB_ENCRYPTION_KEY=$DB_ENCRYPTION_KEY

# Per-container SQLite encryption
SQLITE_MASTER_KEY=$SQLITE_MASTER_KEY

# Integration credentials encryption
CHANNEL_ENCRYPTION_KEY=$CHANNEL_ENCRYPTION_KEY

# ============================================
# AUTHENTICATION SECRETS
# ============================================
# CSRF token signing secret
CSRF_SECRET=$CSRF_SECRET

# Internal API authentication
API_INTERNAL_KEY=$API_INTERNAL_KEY

# ============================================
# REDIS AUTHENTICATION
# ============================================
REDIS_PASSWORD=$REDIS_PASSWORD
REDIS_URL=redis://:$REDIS_PASSWORD@localhost:6379

# ============================================
# JWT RSA-4096 KEYPAIR
# ============================================
# User authentication tokens
RS_PRIVATE_KEY=$RS_PRIVATE_KEY
RS_PUBLIC_KEY=$RS_PUBLIC_KEY

# ============================================
# ADMIN JWT RSA-4096 KEYPAIR
# ============================================
# Admin-only authentication tokens
ADMIN_RS_PRIVATE_KEY=$ADMIN_RS_PRIVATE_KEY
ADMIN_RS_PUBLIC_KEY=$ADMIN_RS_PUBLIC_KEY

# ============================================
# WEBHOOK VERIFICATION TOKENS
# ============================================
WHATSAPP_VERIFY_TOKEN=$WHATSAPP_VERIFY_TOKEN
WHATSAPP_WEBHOOK_SECRET=$WHATSAPP_WEBHOOK_SECRET
FACEBOOK_WEBHOOK_VERIFY_TOKEN=$FACEBOOK_WEBHOOK_VERIFY_TOKEN

# ============================================
# NEXT STEPS
# ============================================
# 1. Copy these values to your .env file:
#    cat .env.generated >> .env
#
# 2. Add remaining configuration (see .env.example):
#    - DATABASE_URL
#    - OPENAI_API_KEY
#    - STRIPE_SECRET_KEY
#    - OAuth2 credentials
#    - Third-party API keys
#
# 3. DELETE this file:
#    rm .env.generated
#
# 4. Verify configuration:
#    docker-compose config
#    docker-compose up -d
# ============================================
EOF

echo ""
echo "=================================="
echo "✅ Secrets generation complete!"
echo "=================================="
echo ""
echo "📄 Secrets saved to: $OUTPUT_FILE"
echo ""
echo "⚠️  IMPORTANT NEXT STEPS:"
echo ""
echo "1. Copy secrets to .env file:"
echo "   cat $OUTPUT_FILE >> .env"
echo ""
echo "2. Add remaining configuration (database, API keys, etc.):"
echo "   nano .env"
echo ""
echo "3. DELETE the generated file:"
echo "   rm $OUTPUT_FILE"
echo ""
echo "4. Verify and start services:"
echo "   docker-compose up -d"
echo ""
echo "⚠️  SECURITY WARNING:"
echo "   Keep $OUTPUT_FILE secure and delete after use!"
echo "   Never commit to version control!"
echo ""
