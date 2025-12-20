# motocore

**Modular botocore for size-constrained environments**

[![Python](https://img.shields.io/pypi/pyversions/motocore.svg?style=flat)](https://pypi.python.org/pypi/motocore/)
[![License](https://img.shields.io/pypi/l/motocore.svg?style=flat)](LICENSE.txt)

motocore is a modular fork of [botocore](https://github.com/boto/botocore) that reduces package size from **111 MB to as little as 2.5 MB** for single-service use cases. It's designed for AWS Lambda and other size-constrained environments where the full botocore/boto3 package is too large.

## The Problem

The standard botocore package includes service definitions for all 400+ AWS services, resulting in a 111 MB installation. For a Lambda function that only uses DynamoDB, this is significant overhead:

| Component | Size |
|-----------|------|
| Service definitions (all 415 services) | 104 MB |
| Core Python modules | ~1.2 MB |
| Endpoints configuration | 1.2 MB |
| SSL certs, vendored libs | ~0.5 MB |
| **Total botocore** | **~111 MB** |

## The Solution

motocore splits botocore into modular packages, and **moto3** provides a convenient wrapper:

| Package | Size | Description |
|---------|------|-------------|
| `moto3-dynamodb` | 3.5 MB | Complete solution: moto3 + motocore-core + DynamoDB |
| `moto3-bundle-serverless` | 6.0 MB | moto3 + common serverless services |
| `motocore-core` | 2.9 MB | Core SDK functionality (for boto3 users) |
| `motocore-dynamodb` | 600 KB | DynamoDB service definitions only |
| `motocore` | 111 MB | Full package (backwards compatible) |

**Result**: A Lambda function using only DynamoDB needs just **~3.5 MB** instead of 111 MB.

## Installation

### Recommended: Use moto3 (simplest)

```bash
# Single service
pip install moto3-dynamodb

# Multiple services - use a bundle
pip install moto3-bundle-serverless

# All services
pip install moto3-full
```

### Alternative: Use with existing boto3

If you're already using boto3, you can install motocore packages directly:

```bash
# Core + single service
pip install boto3 motocore-core motocore-dynamodb

# Core + multiple services
pip install boto3 motocore-core motocore-dynamodb motocore-s3 motocore-sqs

# Core + a bundle (common service combinations)
pip install boto3 motocore-core motocore-bundle-serverless
```

### For Full Compatibility

Install everything (equivalent to standard botocore):

```bash
pip install motocore
```

## Usage with boto3

motocore is a drop-in replacement for botocore. When you install motocore packages, they register themselves via Python entry points and boto3 discovers them automatically.

### Basic Usage

```python
import boto3

# Works exactly like standard boto3
# (requires motocore-core + motocore-dynamodb installed)
dynamodb = boto3.client('dynamodb', region_name='us-east-1')
response = dynamodb.list_tables()
print(response['TableNames'])
```

### Using boto3 Resource API

```python
import boto3

# Resource API works too
# (requires motocore-core + motocore-dynamodb installed)
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('my-table')
response = table.get_item(Key={'id': '123'})
```

### Lambda Function Example

**Using moto3 (recommended):**

```python
# requirements.txt:
# moto3-dynamodb
# moto3-sqs

import moto3 as boto3
import json

dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')

def handler(event, context):
    # Use DynamoDB
    table = dynamodb.Table('my-table')
    table.put_item(Item={'id': event['id'], 'data': event['data']})

    # Use SQS
    sqs.send_message(
        QueueUrl='https://sqs.us-east-1.amazonaws.com/123456789/my-queue',
        MessageBody=json.dumps(event)
    )

    return {'statusCode': 200}
```

**Using boto3 with motocore:**

```python
# requirements.txt:
# boto3
# motocore-core
# motocore-dynamodb
# motocore-sqs

import boto3  # Works unchanged - motocore is auto-discovered
import json

dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')

def handler(event, context):
    table = dynamodb.Table('my-table')
    table.put_item(Item={'id': event['id'], 'data': event['data']})
    # ...
```

## moto3: Convenience Wrapper

For the cleanest installation experience, use **moto3** - a thin boto3 wrapper that depends on motocore:

```bash
# Single install for DynamoDB support
pip install moto3-dynamodb

# Or use a bundle
pip install moto3-bundle-serverless
```

Then use it as a drop-in replacement for boto3:

```python
import moto3 as boto3

# Same API as boto3, but with modular motocore under the hood
dynamodb = boto3.client('dynamodb')
s3 = boto3.resource('s3')
```

### moto3 Package Hierarchy

```
moto3                           # Base: boto3 wrapper + motocore-core
├── moto3-dynamodb             # moto3 + motocore-dynamodb
├── moto3-s3                   # moto3 + motocore-s3
├── moto3-bundle-serverless    # moto3 + motocore-bundle-serverless
└── moto3-full                 # moto3 + all services
```

### Generating moto3 Packages

```bash
# Generate base moto3 package
python scripts/generate_moto3_package.py --base

# Generate service package
python scripts/generate_moto3_package.py --service dynamodb

# Generate bundle package
python scripts/generate_moto3_package.py --bundle serverless

# Generate all packages
python scripts/generate_moto3_package.py --all
```

## Available Packages

### Individual Services

Each AWS service is available as a separate package:

```
motocore-dynamodb      # DynamoDB (600 KB)
motocore-s3            # S3 (2.1 MB)
motocore-lambda        # Lambda
motocore-sqs           # SQS
motocore-sns           # SNS
motocore-sts           # STS
motocore-logs          # CloudWatch Logs
motocore-ec2           # EC2 (9.1 MB - largest service)
motocore-rds           # RDS
motocore-iam           # IAM
# ... and 400+ more
```

### Service Bundles

Pre-configured bundles for common use cases:

| Bundle | Services | Size |
|--------|----------|------|
| `motocore-bundle-minimal-lambda` | sts, logs | 687 KB |
| `motocore-bundle-lambda-dynamodb` | dynamodb, sts, logs | 1.3 MB |
| `motocore-bundle-lambda-s3` | s3, sts, logs | 2.8 MB |
| `motocore-bundle-serverless` | lambda, dynamodb, apigateway, sqs, sns, stepfunctions, sts, logs, events | 3.0 MB |
| `motocore-bundle-lambda-full` | lambda, dynamodb, s3, sqs, sns, sts, logs, events | 4.8 MB |
| `motocore-bundle-containers` | ecs, ecr, eks, batch | 1.6 MB |
| `motocore-bundle-database` | dynamodb, rds, elasticache, neptune, docdb, redshift, etc. | 4.5 MB |
| `motocore-bundle-ml` | sagemaker, bedrock, rekognition, comprehend, translate, etc. | 4.4 MB |

## Replacing botocore in Existing Projects

### Method 1: Direct Installation (Recommended)

Simply install motocore packages. They use the `botocore` namespace, so existing code works unchanged:

```bash
# Uninstall standard botocore
pip uninstall botocore

# Install modular motocore
pip install motocore-core motocore-dynamodb motocore-s3
```

Your existing code continues to work:

```python
# This still works - no code changes needed
import botocore.session
import boto3
```

### Method 2: Requirements File

Update your `requirements.txt`:

```txt
# Before
boto3
botocore

# After
boto3
motocore-core
motocore-dynamodb
motocore-s3
```

### Method 3: Poetry/pyproject.toml

```toml
[tool.poetry.dependencies]
boto3 = "^1.26"
motocore-core = "^1.0"
motocore-dynamodb = "^1.0"
motocore-s3 = "^1.0"
```

## How It Works

motocore uses Python [entry points](https://packaging.python.org/en/latest/specifications/entry-points/) to register service packages with botocore. When you install a service package like `motocore-dynamodb`, it registers itself:

```toml
# In motocore-dynamodb's pyproject.toml
[project.entry-points."botocore.services"]
dynamodb = "motocore_dynamodb:register"
```

When boto3/botocore needs service definitions, it discovers installed packages via entry points and loads only what's needed.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         boto3                                │
├─────────────────────────────────────────────────────────────┤
│                     motocore-core                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │   Session   │ │   Client    │ │  Credentials, Signing   ││
│  │   Loader    │ │   Factory   │ │  Endpoints, Handlers    ││
│  └─────────────┘ └─────────────┘ └─────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│              Service Packages (via entry points)             │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐   │
│  │ dynamodb  │ │    s3     │ │   sqs     │ │    ...    │   │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Generating Custom Packages

You can generate your own service packages or bundles:

```bash
# Generate a single service package
python scripts/generate_service_package.py dynamodb ./dist

# Generate a bundle
python scripts/generate_bundle_package.py serverless ./dist

# Generate all service packages
python scripts/generate_service_package.py --all ./dist

# List available services and sizes
python scripts/generate_service_package.py --show-sizes
```

## Compatibility

- **100% API compatible** with botocore and boto3
- All existing code works unchanged
- All botocore tests pass
- Supports Python 3.9+

## Benchmarks

| Scenario | Standard botocore | motocore | Savings |
|----------|-------------------|----------|---------|
| Lambda cold start (DynamoDB only) | ~2-3s | ~300ms | 85-90% |
| Package size (DynamoDB only) | 111 MB | 3.5 MB | 97% |
| Import time | ~500ms | ~50ms | 90% |

## Development

```bash
# Clone the repository
git clone https://github.com/ryantenney/motocore.git
cd motocore

# Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Run tests
python -m pytest tests/unit/

# Generate packages
python scripts/generate_core_package.py ./dist/packages
python scripts/generate_service_package.py dynamodb ./dist/packages
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.rst](CONTRIBUTING.rst) for guidelines.

## License

Apache License 2.0 - see [LICENSE.txt](LICENSE.txt)

## Acknowledgments

motocore is a fork of [botocore](https://github.com/boto/botocore), maintained by Amazon Web Services. This project adds modularization while maintaining full compatibility.
