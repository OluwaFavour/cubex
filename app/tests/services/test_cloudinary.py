"""
Test suite for CloudinaryService file management service.

This module contains comprehensive tests for the Cloudinary file service including:
- Service initialization with credentials
- File upload with various configurations
- Single file deletion
- Batch file deletion
- Error handling and logging

Run all tests:
    pytest app/tests/services/test_cloudinary.py -v

Run with coverage:
    pytest app/tests/services/test_cloudinary.py --cov=app.shared.services.cloudinary --cov-report=term-missing -v
"""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from fastapi import UploadFile, status

from app.shared.services.cloudinary import CloudinaryService
from app.shared.exceptions.types import AppException


class TestCloudinaryServiceInit:
    """Test suite for CloudinaryService initialization."""

    def test_init_configures_cloudinary(self):
        """Test that init properly configures cloudinary with credentials."""
        with patch("app.shared.services.cloudinary.cloudinary.config") as mock_config:
            CloudinaryService.init(
                cloud_name="test-cloud",
                api_key="test-key-123",
                api_secret="test-secret-456",
            )

            mock_config.assert_called_once_with(
                cloud_name="test-cloud",
                api_key="test-key-123",
                api_secret="test-secret-456",
            )

    def test_init_with_all_parameters(self):
        """Test init accepts all required parameters."""
        with patch("app.shared.services.cloudinary.cloudinary.config") as mock_config:
            CloudinaryService.init(
                cloud_name="my-cloud", api_key="my-api-key", api_secret="my-api-secret"
            )

            call_kwargs = mock_config.call_args[1]
            assert call_kwargs["cloud_name"] == "my-cloud"
            assert call_kwargs["api_key"] == "my-api-key"
            assert call_kwargs["api_secret"] == "my-api-secret"


class TestCloudinaryServiceUploadFile:
    """Test suite for file upload functionality."""

    @pytest.mark.asyncio
    async def test_upload_file_success(self):
        """Test successful file upload to Cloudinary."""
        # Create a mock UploadFile
        mock_file = MagicMock(spec=UploadFile)
        mock_file.file = BytesIO(b"test file content")
        mock_file.filename = "test.jpg"

        mock_upload_result = {
            "secure_url": "https://cloudinary.com/image/test.jpg",
            "public_id": "test_image_id",
            "resource_type": "image",
        }

        with patch(
            "app.shared.services.cloudinary.cloudinary.uploader.upload"
        ) as mock_upload, patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.return_value = mock_upload_result

            secure_url, public_id, resource_type = await CloudinaryService.upload_file(
                mock_file
            )

            assert secure_url == "https://cloudinary.com/image/test.jpg"
            assert public_id == "test_image_id"
            assert resource_type == "image"
            mock_run_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_file_with_folder(self):
        """Test file upload with folder parameter."""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.file = BytesIO(b"test content")

        mock_upload_result = {
            "secure_url": "https://cloudinary.com/uploads/test.jpg",
            "public_id": "uploads/test_id",
            "resource_type": "image",
        }

        # Track the actual upload function that gets called
        captured_upload_func = None
        captured_kwargs = None

        async def mock_run_sync(func, *args, **kwargs):
            nonlocal captured_upload_func, captured_kwargs
            captured_upload_func = func
            # Call the actual upload function to test folder logic
            result = func(*args, **kwargs)
            return mock_upload_result

        with patch(
            "app.shared.services.cloudinary.cloudinary.uploader.upload"
        ) as mock_upload, patch(
            "app.shared.services.cloudinary.run_sync", side_effect=mock_run_sync
        ):
            mock_upload.return_value = mock_upload_result

            secure_url, public_id, resource_type = await CloudinaryService.upload_file(
                mock_file, folder="uploads", transformation={"width": 500}
            )

            assert secure_url == "https://cloudinary.com/uploads/test.jpg"
            assert public_id == "uploads/test_id"
            # Verify upload was called with folder
            mock_upload.assert_called_once()
            call_kwargs = mock_upload.call_args[1]
            assert call_kwargs["folder"] == "uploads"

    @pytest.mark.asyncio
    async def test_upload_file_with_kwargs(self):
        """Test file upload with additional kwargs."""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.file = BytesIO(b"test content")

        mock_upload_result = {
            "secure_url": "https://cloudinary.com/test.jpg",
            "public_id": "test_id",
            "resource_type": "image",
        }

        with patch(
            "app.shared.services.cloudinary.cloudinary.uploader.upload"
        ) as mock_upload, patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.return_value = mock_upload_result

            await CloudinaryService.upload_file(
                mock_file,
                resource_type="image",
                transformation={"width": 500, "height": 500},
            )

            mock_run_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_file_video(self):
        """Test uploading video file."""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.file = BytesIO(b"video content")
        mock_file.filename = "test.mp4"

        mock_upload_result = {
            "secure_url": "https://cloudinary.com/video/test.mp4",
            "public_id": "video_test_id",
            "resource_type": "video",
        }

        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.return_value = mock_upload_result

            secure_url, public_id, resource_type = await CloudinaryService.upload_file(
                mock_file
            )

            assert resource_type == "video"

    @pytest.mark.asyncio
    async def test_upload_file_raises_exception_on_failure(self):
        """Test that upload failure raises AppException."""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.file = BytesIO(b"test content")

        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.side_effect = Exception("Upload failed: Network error")

            with pytest.raises(AppException) as exc_info:
                await CloudinaryService.upload_file(mock_file)

            assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "File upload failed" in exc_info.value.message
            assert "Network error" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_upload_file_without_folder(self):
        """Test file upload without folder uses default behavior."""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.file = BytesIO(b"test content")

        mock_upload_result = {
            "secure_url": "https://cloudinary.com/test.jpg",
            "public_id": "test_id",
            "resource_type": "image",
        }

        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.return_value = mock_upload_result

            secure_url, public_id, resource_type = await CloudinaryService.upload_file(
                mock_file, folder=None
            )

            assert secure_url == "https://cloudinary.com/test.jpg"


class TestCloudinaryServiceDeleteFile:
    """Test suite for single file deletion."""

    @pytest.mark.asyncio
    async def test_delete_file_success(self):
        """Test successful file deletion from Cloudinary."""

        # Use side_effect to actually call the inner function
        async def mock_run_sync(func, *args):
            # Call the actual destroy function
            return func(*args)

        with patch(
            "app.shared.services.cloudinary.cloudinary.uploader.destroy"
        ) as mock_destroy, patch(
            "app.shared.services.cloudinary.run_sync", side_effect=mock_run_sync
        ):
            mock_destroy.return_value = None

            await CloudinaryService.delete_file("test_public_id")

            mock_destroy.assert_called_once_with("test_public_id")

    @pytest.mark.asyncio
    async def test_delete_file_with_path(self):
        """Test deletion of file with path in public_id."""
        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.return_value = None

            await CloudinaryService.delete_file("folder/subfolder/image_id")

            call_args = mock_run_sync.call_args[0]
            assert call_args[1] == "folder/subfolder/image_id"

    @pytest.mark.asyncio
    async def test_delete_file_raises_exception_on_failure(self):
        """Test that deletion failure raises AppException."""
        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.side_effect = Exception("Deletion failed: Resource not found")

            with pytest.raises(AppException) as exc_info:
                await CloudinaryService.delete_file("nonexistent_id")

            assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "File deletion failed" in exc_info.value.message
            assert "Resource not found" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_delete_file_logs_operation(self):
        """Test that delete_file logs the operation."""
        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync, patch(
            "app.shared.services.cloudinary.cloudinary_logger"
        ) as mock_logger:
            mock_run_sync.return_value = None

            await CloudinaryService.delete_file("test_id")

            # Verify logging occurred
            assert mock_logger.info.call_count == 2  # Before and after deletion
            calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("Deleting file" in str(call) for call in calls)
            assert any("deleted successfully" in str(call) for call in calls)


class TestCloudinaryServiceDeleteFiles:
    """Test suite for batch file deletion."""

    @pytest.mark.asyncio
    async def test_delete_files_success(self):
        """Test successful batch deletion of files."""
        public_ids = ["id1", "id2", "id3"]

        # Use side_effect to actually call the inner function
        async def mock_run_sync(func, *args):
            return func(*args)

        with patch(
            "app.shared.services.cloudinary.cloudinary.api.delete_resources"
        ) as mock_delete, patch(
            "app.shared.services.cloudinary.run_sync", side_effect=mock_run_sync
        ):
            mock_delete.return_value = None

            await CloudinaryService.delete_files(public_ids)

            mock_delete.assert_called_once_with(public_ids)

    @pytest.mark.asyncio
    async def test_delete_files_empty_list(self):
        """Test batch deletion with empty list."""
        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.return_value = None

            await CloudinaryService.delete_files([])

            call_args = mock_run_sync.call_args[0]
            assert call_args[1] == []

    @pytest.mark.asyncio
    async def test_delete_files_single_file(self):
        """Test batch deletion with single file."""
        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.return_value = None

            await CloudinaryService.delete_files(["single_id"])

            call_args = mock_run_sync.call_args[0]
            assert call_args[1] == ["single_id"]

    @pytest.mark.asyncio
    async def test_delete_files_with_paths(self):
        """Test batch deletion of files with folder paths."""
        public_ids = ["folder1/image1", "folder2/subfolder/image2", "root_image"]

        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.return_value = None

            await CloudinaryService.delete_files(public_ids)

            call_args = mock_run_sync.call_args[0]
            assert call_args[1] == public_ids

    @pytest.mark.asyncio
    async def test_delete_files_raises_exception_on_failure(self):
        """Test that batch deletion failure raises AppException."""
        public_ids = ["id1", "id2"]

        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.side_effect = Exception("API error: Rate limit exceeded")

            with pytest.raises(AppException) as exc_info:
                await CloudinaryService.delete_files(public_ids)

            assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "Files deletion failed" in exc_info.value.message
            assert "Rate limit exceeded" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_delete_files_logs_operation(self):
        """Test that delete_files logs the operation."""
        public_ids = ["id1", "id2"]

        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync, patch(
            "app.shared.services.cloudinary.cloudinary_logger"
        ) as mock_logger:
            mock_run_sync.return_value = None

            await CloudinaryService.delete_files(public_ids)

            # Verify logging occurred
            assert mock_logger.info.call_count == 2  # Before and after deletion
            calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("Deleting files" in str(call) for call in calls)
            assert any("deleted successfully" in str(call) for call in calls)

    @pytest.mark.asyncio
    async def test_delete_files_large_batch(self):
        """Test batch deletion with large number of files."""
        # Cloudinary typically has limits, but our service should handle any size
        large_batch = [f"image_{i}" for i in range(100)]

        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.return_value = None

            await CloudinaryService.delete_files(large_batch)

            call_args = mock_run_sync.call_args[0]
            assert len(call_args[1]) == 100


class TestCloudinaryServiceErrorHandling:
    """Test suite for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_upload_file_chained_exception(self):
        """Test that AppException chains original exception."""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.file = BytesIO(b"test")

        original_error = ValueError("Invalid file format")

        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.side_effect = original_error

            with pytest.raises(AppException) as exc_info:
                await CloudinaryService.upload_file(mock_file)

            # Verify exception chaining
            assert exc_info.value.__cause__ is original_error

    @pytest.mark.asyncio
    async def test_delete_file_chained_exception(self):
        """Test that delete_file AppException chains original exception."""
        original_error = ConnectionError("Network failure")

        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.side_effect = original_error

            with pytest.raises(AppException) as exc_info:
                await CloudinaryService.delete_file("test_id")

            assert exc_info.value.__cause__ is original_error

    @pytest.mark.asyncio
    async def test_delete_files_chained_exception(self):
        """Test that delete_files AppException chains original exception."""
        original_error = TimeoutError("Request timeout")

        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.side_effect = original_error

            with pytest.raises(AppException) as exc_info:
                await CloudinaryService.delete_files(["id1", "id2"])

            assert exc_info.value.__cause__ is original_error

    @pytest.mark.asyncio
    async def test_upload_file_includes_error_message_in_exception(self):
        """Test that upload error message is included in AppException."""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.file = BytesIO(b"test")

        with patch(
            "app.shared.services.cloudinary.run_sync", new_callable=AsyncMock
        ) as mock_run_sync:
            mock_run_sync.side_effect = Exception("Specific upload error")

            with pytest.raises(AppException) as exc_info:
                await CloudinaryService.upload_file(mock_file)

            assert "Specific upload error" in str(exc_info.value.message)
            assert "try again" in exc_info.value.message.lower()
