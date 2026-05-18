#!/usr/bin/env node
/**
 * BizOS Environment Validation Script
 *
 * Validates that all required environment variables are set
 * and have valid values before deployment.
 *
 * Usage:
 *   node validate-env.js
 *   npm run validate:env
 */

require('dotenv').config();

const chalk = require('chalk');

// ANSI color codes (if chalk not available)
const colors = {
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m'
};

const log = {
  error: (msg) => console.error(`${colors.red}✗${colors.reset} ${msg}`),
  success: (msg) => console.log(`${colors.green}✓${colors.reset} ${msg}`),
  warn: (msg) => console.warn(`${colors.yellow}⚠${colors.reset} ${msg}`),
  info: (msg) => console.log(`${colors.blue}ℹ${colors.reset} ${msg}`)
};

// Required variables for all environments
const REQUIRED_ALWAYS = [
  'NODE_ENV',
  'DATABASE_URL',
  'REDIS_URL',
  'DB_ENCRYPTION_KEY',
  'CHANNEL_ENCRYPTION_KEY',
  'RS_PRIVATE_KEY',
  'RS_PUBLIC_KEY',
  'OPENAI_API_KEY'
];

// Required only in production
const REQUIRED_PRODUCTION = [
  'ADMIN_RS_PRIVATE_KEY',
  'ADMIN_RS_PUBLIC_KEY',
  'CSRF_SECRET',
  'API_INTERNAL_KEY',
  'STRIPE_SECRET_KEY',
  'STRIPE_WEBHOOK_SECRET',
  'SENTRY_DSN',
  'REDIS_PASSWORD'
];

// Optional but recommended
const RECOMMENDED = [
  'GOOGLE_CLIENT_ID',
  'MICROSOFT_CLIENT_ID',
  'TWILIO_ACCOUNT_SID',
  'POSTMARK_SERVER_TOKEN',
  'DEEPGRAM_API_KEY',
  'CARTESIA_API_KEY'
];

// Validation rules
const VALIDATORS = {
  DB_ENCRYPTION_KEY: (val) => val && val.length === 64 && /^[0-9a-f]{64}$/i.test(val),
  CHANNEL_ENCRYPTION_KEY: (val) => val && val.length === 64 && /^[0-9a-f]{64}$/i.test(val),
  CSRF_SECRET: (val) => val && val.length === 64 && /^[0-9a-f]{64}$/i.test(val),
  API_INTERNAL_KEY: (val) => val && val.length === 64 && /^[0-9a-f]{64}$/i.test(val),
  OPENAI_API_KEY: (val) => val && val.startsWith('sk-or-v1-'),
  STRIPE_SECRET_KEY: (val) => val && (val.startsWith('sk_test_') || val.startsWith('sk_live_')),
  DATABASE_URL: (val) => val && val.startsWith('postgresql://'),
  REDIS_URL: (val) => val && val.startsWith('redis://'),
  RS_PRIVATE_KEY: (val) => val && val.length > 100, // Base64 RSA-4096 is ~6000 chars
  RS_PUBLIC_KEY: (val) => val && val.length > 100
};

// Environment-specific checks
const ENVIRONMENT_CHECKS = {
  production: {
    DEV_MODE: (val) => val === 'false' || val === false,
    DATABASE_SSL: (val) => val === 'true' || val === true,
    STRIPE_SECRET_KEY: (val) => val && val.startsWith('sk_live_'),
    NODE_ENV: (val) => val === 'production'
  },
  development: {
    NODE_ENV: (val) => val === 'development'
  }
};

let errors = 0;
let warnings = 0;
let passed = 0;

console.log('\n🔍 BizOS Environment Validation');
console.log('================================\n');

const env = process.env.NODE_ENV || 'development';
log.info(`Environment: ${env}\n`);

// Check required variables
console.log('Required Variables:');
REQUIRED_ALWAYS.forEach(key => {
  const value = process.env[key];
  const validator = VALIDATORS[key];

  if (!value) {
    log.error(`${key} is not set`);
    errors++;
  } else if (validator && !validator(value)) {
    log.error(`${key} has invalid format`);
    errors++;
  } else if (value.includes('CHANGE_ME') || value.includes('your-') || value === 'dev000000') {
    log.error(`${key} contains placeholder value`);
    errors++;
  } else {
    log.success(key);
    passed++;
  }
});

// Check production-specific requirements
if (env === 'production') {
  console.log('\nProduction Requirements:');
  REQUIRED_PRODUCTION.forEach(key => {
    const value = process.env[key];
    const validator = VALIDATORS[key];

    if (!value) {
      log.error(`${key} is not set (required in production)`);
      errors++;
    } else if (validator && !validator(value)) {
      log.error(`${key} has invalid format`);
      errors++;
    } else if (value.includes('CHANGE_ME') || value.includes('your-')) {
      log.error(`${key} contains placeholder value`);
      errors++;
    } else {
      log.success(key);
      passed++;
    }
  });
}

// Environment-specific validation
const envChecks = ENVIRONMENT_CHECKS[env] || {};
if (Object.keys(envChecks).length > 0) {
  console.log('\nEnvironment-Specific Checks:');
  Object.entries(envChecks).forEach(([key, validator]) => {
    const value = process.env[key];
    if (!validator(value)) {
      log.error(`${key} = "${value}" (invalid for ${env})`);
      errors++;
    } else {
      log.success(`${key} = "${value}"`);
      passed++;
    }
  });
}

// Check recommended variables
console.log('\nRecommended Variables:');
RECOMMENDED.forEach(key => {
  const value = process.env[key];
  if (!value) {
    log.warn(`${key} is not set (optional but recommended)`);
    warnings++;
  } else if (value.includes('CHANGE_ME') || value.includes('your-')) {
    log.warn(`${key} contains placeholder value`);
    warnings++;
  } else {
    log.success(key);
    passed++;
  }
});

// Security checks
console.log('\nSecurity Checks:');
const securityChecks = [
  {
    key: 'RS_PRIVATE_KEY',
    check: () => {
      const key = process.env.RS_PRIVATE_KEY;
      return key && !key.includes('\n') && key.length > 1000;
    },
    message: 'JWT private key must be base64 encoded (no newlines)'
  },
  {
    key: 'REDIS_PASSWORD',
    check: () => {
      const pwd = process.env.REDIS_PASSWORD;
      return pwd && pwd.length >= 16 && !/^(password|admin|redis|dev|test)/i.test(pwd);
    },
    message: 'Redis password must be strong (16+ chars, not common words)'
  },
  {
    key: 'DATABASE_URL',
    check: () => {
      const url = process.env.DATABASE_URL;
      return url && !/password|admin|postgres|dev|test123/i.test(url);
    },
    message: 'Database password should be strong (not common words)'
  }
];

securityChecks.forEach(({ key, check, message }) => {
  if (check()) {
    log.success(message);
    passed++;
  } else {
    log.warn(`${message} (${key})`);
    warnings++;
  }
});

// Summary
console.log('\n================================');
console.log('Validation Summary:');
console.log(`  ${colors.green}✓ Passed:  ${passed}${colors.reset}`);
console.log(`  ${colors.yellow}⚠ Warnings: ${warnings}${colors.reset}`);
console.log(`  ${colors.red}✗ Errors:   ${errors}${colors.reset}`);
console.log('================================\n');

if (errors > 0) {
  log.error(`Validation failed with ${errors} error(s)`);
  log.info('Fix the errors above before deploying');
  process.exit(1);
} else if (warnings > 0) {
  log.warn(`Validation passed with ${warnings} warning(s)`);
  log.info('Review warnings for optional improvements');
  process.exit(0);
} else {
  log.success('All validation checks passed!');
  log.info('Environment configuration is ready for deployment');
  process.exit(0);
}
