import time
from typing import Any

from anyio.to_thread import run_sync
from pydantic import BaseModel

import cloudinary.api
import cloudinary.uploader
import cloudinary.utils
from fastapi import UploadFile, status

from app.core.config import cloudinary_logger
from app.core.exceptions.types import AppException


class CloudinaryUploadCredentials(BaseModel):
    """
    Pydantic model representing the credentials needed for secure client-side uploads to Cloudinary.
    """

    upload_url: str
    api_key: str
    timestamp: int
    signature: str
    cloud_name: str
    folder: str | None = None
    resource_type: str = "auto"
    upload_preset: str | None = None
    eager: str | None = None

    model_config = {"extra": "allow"}


class CloudinaryService:
    @classmethod
    def init(
        cls,
        cloud_name: str,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Initialize the Cloudinary service with the provided credentials.

        Parameters
        ----------
        cloud_name : str
            The Cloudinary cloud name.
        api_key : str
            The Cloudinary API key.
        api_secret : str
            The Cloudinary API secret.

        Returns
        -------
        None
        """
        cls.api_key = api_key
        cls.cloud_name = cloud_name
        cls.api_secret = api_secret
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
        )

    @classmethod
    def generate_upload_credentials(
        cls,
        folder: str | None = None,
        resource_type: str = "auto",
        upload_preset: str | None = None,
        eager: str | None = None,
        **kwargs: Any,
    ) -> CloudinaryUploadCredentials:
        """
        Generate signed upload credentials for secure client-side uploads to Cloudinary.

        This method generates all necessary parameters (signature, timestamp, api_key, etc.)
        that the frontend needs to upload files directly to Cloudinary without exposing
        the API secret.

        Parameters
        ----------
        folder : str | None, optional
            The Cloudinary folder path where the uploaded file will be stored.
        resource_type : str, optional
            The type of resource to upload. Can be "image", "video", "raw", or "auto".
            Defaults to "auto".
        upload_preset : str | None, optional
            An upload preset to use for the upload. If provided, it will be included
            in the signed parameters.
        eager : str | None, optional
            Eager transformations to apply after upload. Format: "transformation1|transformation2".
        **kwargs : Any
            Additional parameters to include in the signature (e.g., public_id,
            transformation, tags, etc.).

        Returns
        -------
        CloudinaryUploadCredentials
            A Pydantic model containing:
                - upload_url: The Cloudinary upload endpoint URL.
                - api_key: The Cloudinary API key (safe to expose).
                - timestamp: The Unix timestamp used for signing.
                - signature: The generated signature for the upload.
                - cloud_name: The Cloudinary cloud name.
                - folder: The target folder (if provided).
                - resource_type: The resource type for the upload.
                - upload_preset: The upload preset (if provided).
                - eager: The eager transformations (if provided).
                - Additional kwargs passed to the method.

        Raises
        ------
        AppException
            If Cloudinary is not configured or signature generation fails.

        Example
        -------
        Frontend usage with the returned credentials:
        ```javascript
        const formData = new FormData();
        formData.append('file', file);
        formData.append('api_key', credentials.api_key);
        formData.append('timestamp', credentials.timestamp);
        formData.append('signature', credentials.signature);
        if (credentials.folder) formData.append('folder', credentials.folder);

        fetch(credentials.upload_url, { method: 'POST', body: formData });
        ```
        """
        try:
            if not cls.cloud_name or not cls.api_key or not cls.api_secret:
                raise AppException(
                    message="Cloudinary is not properly configured.",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            timestamp = int(time.time())

            params_to_sign: dict[str, Any] = {
                "timestamp": timestamp,
            }

            if folder:
                params_to_sign["folder"] = folder
            if upload_preset:
                params_to_sign["upload_preset"] = upload_preset
            if eager:
                params_to_sign["eager"] = eager

            params_to_sign.update(kwargs)

            signature = cloudinary.utils.api_sign_request(
                params_to_sign, cls.api_secret
            )

            upload_url = f"https://api.cloudinary.com/v1_1/{cls.cloud_name}/{resource_type}/upload"

            cloudinary_logger.info(
                "Generated Cloudinary upload credentials successfully."
            )

            return CloudinaryUploadCredentials(
                upload_url=upload_url,
                api_key=cls.api_key,
                timestamp=timestamp,
                signature=signature,
                cloud_name=cls.cloud_name,
                folder=folder,
                resource_type=resource_type,
                upload_preset=upload_preset,
                eager=eager,
                **{k: v for k, v in kwargs.items() if v is not None},
            )

        except AppException:
            raise
        except Exception as e:
            cloudinary_logger.error(f"Failed to generate upload credentials: {str(e)}")
            raise AppException(
                message=f"Failed to generate upload credentials: {str(e)}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from e

    @classmethod
    async def upload_file(
        cls, file: UploadFile, folder: str | None = None, **kwargs
    ) -> tuple[str, str, str]:
        """
        Upload a file to Cloudinary asynchronously.
        This coroutine uploads the provided UploadFile to Cloudinary by delegating the
        blocking cloudinary.uploader.upload call to a synchronous helper run inside
        an async-friendly executor. It returns key pieces of information about the
        uploaded asset on success, and raises an AppException on failure.
        Args:
            cls: Instance reference.
            file (UploadFile): A Starlette/FastAPI UploadFile object. The underlying
                file-like object at file.file will be passed directly to
                cloudinary.uploader.upload.
            folder (str | None, optional): Optional Cloudinary folder path to store the
                uploaded file. If omitted the default Cloudinary folder behavior is used.
            **kwargs: Additional keyword arguments forwarded directly to
                cloudinary.uploader.upload (for example: resource_type, public_id,
                transformation, eager, etc.).
        Returns:
            tuple[str, str, str]: A 3-tuple containing:
                - secure_url: The HTTPS URL of the uploaded asset (result["secure_url"]).
                - public_id: The Cloudinary public identifier for the asset (result["public_id"]).
                - resource_type: The asset resource type (result["resource_type"], e.g. "image" or "video").
        Raises:
            AppException: Raised when the upload fails. The exception includes a
                service-unavailable (HTTP 503) status code and a message derived from
                the underlying error.
        Side effects:
            - Logs upload start, success, and error events using cloudinary_logger.
            - Performs the actual upload via cloudinary.uploader.upload executed in a
              synchronous context bridged to async via run_sync.
        """

        def upload(file: UploadFile, folder: str | None = None, **kwargs) -> dict:
            if folder:
                kwargs["folder"] = folder
            return cloudinary.uploader.upload(
                file.file,
                **kwargs,
            )

        try:
            # Upload file to Cloudinary
            cloudinary_logger.info("Uploading file to Cloudinary.")
            result = await run_sync(
                upload,
                file,
                folder,
            )
            cloudinary_logger.info(f"File uploaded successfully: {result}")
            return result["secure_url"], result["public_id"], result["resource_type"]
        except Exception as e:
            cloudinary_logger.error(f"File upload failed: {str(e)}")
            raise AppException(
                f"Please, try again. File upload failed: {str(e)}",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from e

    @classmethod
    async def delete_file(cls, public_id: str) -> None:
        """
        Asynchronously delete an file from Cloudinary.

        Parameters
        ----------
        cls : Instance Reference.
        public_id : str
            The Cloudinary public identifier of the file to remove.

        Returns
        -------
        None

        Raises
        ------
        Exception
            If the deletion fails, an Exception is raised with an error message and
            the original exception chained.

        Notes
        -----
        - Logs informational messages before and after the deletion attempt.
        - Uses `run_sync` to invoke the synchronous `cloudinary.uploader.destroy`
          from an async context.
        """

        def destroy(public_id: str) -> None:
            cloudinary.uploader.destroy(public_id)

        try:
            cloudinary_logger.info(
                f"Deleting file with public_id {public_id} from Cloudinary."
            )
            await run_sync(
                destroy,
                public_id,
            )
            cloudinary_logger.info(
                f"File with public_id {public_id} deleted successfully."
            )
        except Exception as e:
            cloudinary_logger.error(f"File deletion failed: {str(e)}")
            raise AppException(
                message=f"Please, try again. File deletion failed on Cloudinary: {str(e)}",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from e

    @classmethod
    async def delete_files(cls, public_ids: list[str]) -> None:
        """
        Asynchronously delete multiple files from Cloudinary.

        Parameters
        ----------
        public_ids : list[str]
            A list of Cloudinary public identifiers of the files to remove.

        Returns
        -------
        None

        Raises
        ------
        Exception
            If the deletion fails, an Exception is raised with an error message and
            the original exception chained.

        Notes
        -----
        - Logs informational messages before and after the deletion attempt.
        - Uses `run_sync` to invoke the synchronous `cloudinary.uploader.destroy`
          from an async context.
        """

        def delete_resources(public_ids: list[str]) -> None:
            cloudinary.api.delete_resources(public_ids)

        try:
            cloudinary_logger.info(
                f"Deleting files with public_ids {public_ids} from Cloudinary."
            )
            await run_sync(
                delete_resources,
                public_ids,
            )
            cloudinary_logger.info(
                f"Files with public_ids {public_ids} deleted successfully."
            )
        except Exception as e:
            cloudinary_logger.error(f"Files deletion failed: {str(e)}")
            raise AppException(
                message=f"Please, try again. Files deletion failed on Cloudinary: {str(e)}",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            ) from e

