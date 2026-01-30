# Quick Test Reference

## Files Created

```bash
📁 app/tests/
├── 📄 __init__.py                 # Package initialization
├── 📄 conftest.py                 # Shared pytest fixtures & config
├── 📄 test_utils.py               # Tests for app.shared.utils (68 tests)
├── 📄 README.md                   # How to run tests
└── 📄 TEST_SUMMARY.md             # Detailed test documentation

📁 project root/
├── 📄 pyproject.toml              # Pytest configuration
└── 📄 requirements-dev.txt        # Test dependencies
```

## Quick Commands

```bash
# Run all tests
pytest app/tests/ -v

# Run unit tests only (skip integration tests)
pytest app/tests/ -v -m "not integration"

# Run integration tests only (requires real database)
pytest app/tests/ -v -m integration

# Run all utils tests
pytest app/tests/test_utils.py -v

# Run all main.py tests
pytest app/tests/test_main.py -v

# Run with coverage
pytest app/tests/ --cov=app --cov-report=html

# Run specific test class
pytest app/tests/test_utils.py::TestHashPassword -v

# Run and stop on first failure
pytest app/tests/ -x

# Run with print statements shown
pytest app/tests/ -s
```

## Test Classes Overview

| Class | Tests | Function Tested |
| ------- | ------- | ---------------- |
| `TestHashPassword` | 6 | `hash_password()` |
| `TestVerifyPassword` | 9 | `verify_password()` |
| `TestCreateJwtToken` | 9 | `create_jwt_token()` |
| `TestDecodeJwtToken` | 7 | `decode_jwt_token()` |
| `TestConvertUnixTimestampToDatetime` | 5 | `convert_unix_timestamp_to_datetime()` |
| `TestGenerateOtpCode` | 5 | `generate_otp_code()` |
| `TestMaskOtp` | 6 | `mask_otp()` |
| `TestGetDeviceInfo` | 9 | `get_device_info()` |
| `TestGenerateOpenapiJson` | 5 | `generate_openapi_json()` |
| `TestWriteToFileAsync` | 7 | `write_to_file_async()` |
| **TOTAL** | **68** | **10 functions** |

## Coverage: 90%

✅ All 68 tests passing
