# Quick Test Reference

## Test Suite Structure

```bash
📁 app/tests/ (283 tests total)
├── 📄 __init__.py                                # Package initialization
├── 📄 conftest.py                                # Shared fixtures & config
├── 📄 README.md                                  # How to run tests
├── 📄 TEST_SUMMARY.md                            # Detailed documentation
├── 📄 QUICK_REFERENCE.md                         # This file
├── 📄 test_main.py                               # Main app (33 tests)
├── 📄 test_utils.py                              # Utils (76 tests)
├── 📁 core/
│   └── 📄 test_dependencies.py                   # Dependencies (3 tests)
├── 📁 services/
│   ├── 📄 test_brevo.py                         # Email service (41 tests)
│   ├── 📄 test_cloudinary.py                    # File service (23 tests)
│   └── 📄 test_template.py                      # Templates (17 tests)
├── 📁 infrastructure/
│   ├── 📁 messaging/
│   │   ├── 📄 test_connection.py                # RabbitMQ (5 tests)
│   │   ├── 📄 test_queues.py                    # Queues (17 tests)
│   │   ├── 📄 test_publisher.py                 # Publisher (7 tests)
│   │   ├── 📄 test_consumer.py                  # Consumer (13 tests)
│   │   └── 📄 test_main.py                      # Startup (10 tests)
│   └── 📁 scheduler/
│       └── 📄 test_main.py                      # Scheduler (4 tests)
└── 📁 shared/
    ├── � test_logger.py                        # Logger (17 tests)
    ├── �📁 db/
    │   └── 📄 test_config.py                    # DB config (7 tests)
    └── 📁 exceptions/
        ├── 📄 test_types.py                     # Exceptions (8 tests)
        └── 📄 test_handlers.py                  # Handlers (5 tests)

📁 project root/
├── 📄 pyproject.toml                            # Pytest configuration
└── 📄 requirements-dev.txt                      # Test dependencies
```

## Quick Commands

```bash
# Run all tests (283 tests)
pytest app/tests/ -v

# Run with coverage (100% coverage)
pytest app/tests/ --cov=app --cov-report=html
pytest app/tests/ --cov=app --cov-report=term-missing

# Run unit tests only (skip integration tests)
pytest app/tests/ -v -m "not integration"

# Run integration tests only (requires TEST_DATABASE_URL in .env)
pytest app/tests/ -v -m integration

# Run specific modules
pytest app/tests/test_utils.py -v                              # Utils (76 tests)
pytest app/tests/test_main.py -v                               # Main (33 tests)
pytest app/tests/services/ -v                                  # Services (81 tests)
pytest app/tests/infrastructure/messaging/ -v                   # Messaging (49 tests)
pytest app/tests/infrastructure/scheduler/ -v                   # Scheduler (4 tests)
pytest app/tests/core/ -v                                      # Core (3 tests)
pytest app/tests/shared/ -v                                    # Shared (20 tests)

# Run specific test files
pytest app/tests/services/test_brevo.py -v                     # Brevo (41 tests)
pytest app/tests/infrastructure/messaging/test_consumer.py -v  # Consumer (13 tests)

# Run specific test class
pytest app/tests/test_utils.py::TestHashPassword -v

# Run and stop on first failure
pytest app/tests/ -x

# Run with print statements shown
pytest app/tests/ -s

# Run quietly (minimal output)
pytest app/tests/ -q
```

## Test Statistics by Module

| Module | Tests | Coverage | Files |
| ------ | ----- | -------- | ----- |
| **Core** | 3 | 100% | 1 |
| **Main App** | 33 | 100% | 1 |
| **Utils** | 76 | 100% | 1 |
| **Services** | 81 | 100% | 3 |
| ├─ Brevo | 41 | 100% | 1 |
| ├─ Cloudinary | 23 | 100% | 1 |
| └─ Template | 17 | 100% | 1 |
| **Infrastructure** | 53 | 100% | 6 |
| ├─ Messaging | 49 | 100% | 5 |
| └─ Scheduler | 4 | 100% | 1 |
| **Shared** | 37 | 100% | 4 |
| ├─ Database | 7 | 100% | 1 |
| ├─ Logger | 17 | 100% | 1 |
| └─ Exceptions | 13 | 100% | 2 |
| **TOTAL** | **283** | **100%** | **16** |

## Coverage: 100% 🎉

✅ All 283 tests passing  
✅ 676/676 statements covered  
✅ 0 missing lines
