from typing import (
    Any,
    TypeVar,
    Generic,
    Type,
    Sequence,
    Callable,
)
from uuid import UUID

from sqlalchemy import (
    SQLColumnExpression,
    UnaryExpression,
    and_,
    or_,
    update as sa_update,
    delete as sa_delete,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.expression import asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import Select, Delete, Update

from app.shared.exceptions.types import DatabaseException

T = TypeVar("T")


class BaseDB(Generic[T]):
    def __init__(self, model: Type[T]):
        self.model = model

    async def get_by_id(
        self, session: AsyncSession, id: UUID, options: list[Any] = []
    ) -> T | None:
        """
        Asynchronously retrieves an instance of the model by its primary key.

        Args:
            session (AsyncSession): The asynchronous database session to use for the query.
            id (UUID): The primary key value of the model instance to retrieve.
            options (list[Any], optional): A list of SQLAlchemy loader options (e.g., selectinload). Defaults to an empty list.

        Returns:
            T | None: The model instance if found, otherwise None.

        Raises:
            DatabaseException: If an error occurs while querying the database.
        """
        try:
            # If loader options (e.g. selectinload) are provided, use an explicit select
            stmt: Select = (
                select(self.model)
                .options(*options)
                .where(getattr(self.model, "id") == id)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                f"Error retrieving {self.model.__name__} with ID {id}: {str(e)}"
            ) from e

    async def get_all(
        self,
        session: AsyncSession,
        filters: list[Any] | None = None,
        order_by: list[Any] | None = None,
        last_values: tuple | None = None,
        limit: int | None = None,
        options: list[Any] = [],
    ) -> Sequence[T]:
        """
        Retrieve paginated and filtered results from the DB using keyset pagination.

        Args:
            session: Async SQLAlchemy session.
            filters: list of additional filters to apply.
            order_by: list of columns/expressions to order by (must be deterministic).
            last_values: tuple of last seen values for keyset pagination.
            limit: Max number of records to return.
            options: list of SQLAlchemy loader options (e.g., selectinload).

        Returns:
            A sequence of model instances.
        """
        try:
            stmt = select(self.model).options(*options)

            # Apply filters
            if filters:
                stmt = stmt.filter(*filters)

            # Apply keyset pagination
            if order_by and last_values:
                assert len(order_by) == len(last_values), "Cursor length mismatch"
                keyset_conditions = []

                for i, col in enumerate(order_by):
                    # Detect asc/desc
                    if isinstance(col, UnaryExpression) and col.modifier == desc:
                        is_desc = True
                        base_col = col.element
                    elif isinstance(col, UnaryExpression) and col.modifier == asc:
                        is_desc = False
                        base_col = col.element
                    else:  # default = ascending
                        is_desc = False
                        base_col = col

                    # Prefix match for earlier columns
                    condition = tuple(
                        (
                            order_by[j].element
                            if isinstance(order_by[j], UnaryExpression)
                            else order_by[j]
                        )
                        == last_values[j]
                        for j in range(i)
                    )
                    prefix_match = and_(*condition) if condition else True

                    # Flip comparator based on order direction
                    cmp = (
                        base_col < last_values[i]
                        if is_desc
                        else base_col > last_values[i]
                    )

                    keyset_conditions.append(and_(prefix_match, cmp))

                stmt = stmt.filter(or_(*keyset_conditions))

            # Apply ordering
            if order_by:
                stmt = stmt.order_by(*order_by)

            # Apply limit
            if limit:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            return result.scalars().all()

        except SQLAlchemyError as e:
            raise DatabaseException(
                f"Error retrieving all {self.model.__name__} records: {str(e)}"
            ) from e

    async def get_by_filters(
        self,
        session: AsyncSession,
        filters: dict,
        order_by: list[SQLColumnExpression] | None = None,
        options: list[Any] = [],
    ) -> Sequence[T]:
        """
        Asynchronously retrieves records of the model that match the given filters.

        Args:
            session (AsyncSession): The asynchronous database session to use for the query.
            filters (dict): A dictionary of filter conditions to apply to the query.
            order_by (list[SQLColumnExpression] | None, optional): A list of SQLAlchemy expressions to order the results. Defaults to None.
            options (list[Any], optional): A list of SQLAlchemy loader options (e.g., selectinload). Defaults to empty list.

        Returns:
            Sequence[T]: A sequence containing instances of the model that match the filters.

        Raises:
            DatabaseException: If an error occurs while querying the database.
        """
        try:
            stmt = (
                select(self.model)
                .options(*options)
                .filter_by(**filters)
                .order_by(*order_by)
                if order_by
                else select(self.model).options(*options).filter_by(**filters)
            )
            result = await session.execute(stmt)
            return result.scalars().all()
        except (SQLAlchemyError, ValueError) as e:
            raise DatabaseException(
                f"Error retrieving {self.model.__name__} with filters {filters}: {str(e)}"
            ) from e

    async def get_one_by_filters(
        self, session: AsyncSession, filters: dict, options: list[Any] = []
    ) -> T | None:
        """
        Asynchronously retrieves a single record of the model that matches the given filters.

        Args:
            session (AsyncSession): The asynchronous database session to use for the query.
            filters (dict): A dictionary of filter conditions to apply to the query.
            options (list[Any], optional): A list of SQLAlchemy loader options (e.g., selectinload). Defaults to empty list.

        Returns:
            T | None: An instance of the model if found, otherwise None.

        Raises:
            DatabaseException: If an error occurs while querying the database.
        """
        try:
            stmt = select(self.model).options(*options).filter_by(**filters)
            result = await session.execute(stmt)
            return result.scalars().first()
        except (SQLAlchemyError, ValueError) as e:
            raise DatabaseException(
                f"Error retrieving one {self.model.__name__} with filters {filters}: {str(e)}"
            ) from e

    async def get_by_conditions(
        self,
        session: AsyncSession,
        conditions: list[SQLColumnExpression],
        options: list[Any] = [],
    ) -> Sequence[T]:
        """
        Asynchronously retrieves records of the model that match the given conditions.

        Args:
            session (AsyncSession): The asynchronous database session to use for the query.
            conditions (list[SQLColumnExpression]): A list of SQLAlchemy expressions to filter the query.
            options (list[Any], optional): A list of SQLAlchemy loader options (e.g., selectinload). Defaults to empty list.

        Returns:
            Sequence[T]: A sequence containing instances of the model that match the conditions.

        Raises:
            DatabaseException: If an error occurs while querying the database.
        """
        try:
            stmt = select(self.model).options(*options).where(and_(*conditions))
            result = await session.execute(stmt)
            return result.scalars().all()
        except (SQLAlchemyError, ValueError) as e:
            raise DatabaseException(
                f"Error retrieving {self.model.__name__} with conditions {conditions}: {str(e)}"
            ) from e

    async def get_one_by_conditions(
        self,
        session: AsyncSession,
        conditions: list[SQLColumnExpression],
        options: list[Any] = [],
    ) -> T | None:
        """
        Asynchronously retrieves a single record of the model that matches the given conditions.

        Args:
            session (AsyncSession): The asynchronous database session to use for the query.
            conditions (list[SQLColumnExpression]): A list of SQLAlchemy expressions to filter the query.
            options (list[Any], optional): A list of SQLAlchemy loader options (e.g., selectinload). Defaults to empty list.

        Returns:
            T | None: An instance of the model if found, otherwise None.

        Raises:
            DatabaseException: If an error occurs while querying the database.
        """
        try:
            stmt = select(self.model).options(*options).where(and_(*conditions))
            result = await session.execute(stmt)
            return result.scalars().first()
        except (SQLAlchemyError, ValueError) as e:
            raise DatabaseException(
                f"Error retrieving one {self.model.__name__} with conditions {conditions}: {str(e)}"
            ) from e

    async def create(
        self,
        session: AsyncSession,
        data: dict,
        validate: Callable[[dict], dict] | None = None,
        commit_self: bool = True,
    ) -> T:
        """
        Asynchronously creates and persists a new instance of the model using the provided data.
        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session to use for database operations.
            data (dict): A dictionary of fields and values to initialize the model instance.
            validate (Callable[[dict], dict] | None, optional): An optional callable to validate or transform the input data before model instantiation. Defaults to None.
            commit_self (bool, optional): If True, commits the transaction and refreshes the object from the database. If False, only flushes the session. Defaults to True.
        Returns:
            T: The newly created and persisted model instance.
        Raises:
            DatabaseException: If an error occurs while creating the model instance or committing the transaction.
        """
        try:
            if validate:
                data = validate(data)

            obj = self.model(**data)
            session.add(obj)

            if commit_self:
                await session.commit()
            else:
                await session.flush()

            await session.refresh(obj)
            return obj
        except (SQLAlchemyError, ValueError) as e:
            raise DatabaseException(
                f"Error creating {self.model.__name__}: {str(e)}"
            ) from e

    async def bulk_create(
        self, session: AsyncSession, objects: list[T], commit_self: bool = True
    ) -> list[T]:
        """
        Asynchronously creates multiple instances of the model using the provided objects.

        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session to use for database operations.
            objects (list[T]): A list of model instances to create.
            commit_self (bool, optional): If True, commits the transaction and refreshes the objects from the database.
                If False, only flushes the session. Defaults to True.

        Returns:
            list[T]: The list of newly created and persisted model instances.

        Raises:
            DatabaseException: If an error occurs while creating the model instances or committing the transaction.
        """
        try:
            session.add_all(objects)

            if commit_self:
                await session.commit()
            else:
                await session.flush()

            for obj in objects:
                await session.refresh(obj)
            return objects
        except (SQLAlchemyError, ValueError) as e:
            raise DatabaseException(
                f"Error creating {self.model.__name__} instances: {str(e)}"
            ) from e

    async def update(
        self, session: AsyncSession, id: UUID, updates: dict, commit_self: bool = True
    ) -> T | None:
        """
        Asynchronously updates a record in the database with the given ID using the provided updates.
        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session to use for the update operation.
            id (UUID): The unique identifier of the record to update.
            updates (dict): A dictionary containing the fields and their new values to update in the record.
            commit_self (bool, optional): If True, commits the transaction after the update; otherwise, flushes the session. Defaults to True.
        Returns:
            T | None: The updated record as an instance of the model, or None if no record was found with the given ID.
        Raises:
            DatabaseException: If an error occurs while updating the record or committing the transaction.
        """
        try:
            stmt: Update = (
                sa_update(self.model)
                .where(self.model.id == id)
                .values(**updates)
                .returning(self.model)
            )
            result = await session.execute(stmt)

            if commit_self:
                await session.commit()
            else:
                await session.flush()

            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                f"Error updating {self.model.__name__} with ID {id}: {str(e)}"
            ) from e

    async def update_by_filters(
        self,
        session: AsyncSession,
        filters: dict,
        updates: dict,
        commit_self: bool = True,
    ) -> int:
        """
        Asynchronously updates records in the database that match the given filters with the provided updates.
        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session to use for the update operation.
            filters (dict): A dictionary of filter conditions to locate the records to update.
            updates (dict): A dictionary containing the fields and their new values to update in the records.
            commit_self (bool, optional): If True, commits the transaction after the update; otherwise, flushes the session. Defaults to True.
        Returns:
            int: The number of records updated.
        Raises:
            DatabaseException: If an error occurs while updating the records or committing the transaction.
        """
        try:
            stmt: Update = (
                sa_update(self.model)
                .where(and_(*[getattr(self.model, k) == v for k, v in filters.items()]))
                .values(**updates)
            )
            result = await session.execute(stmt)

            if commit_self:
                await session.commit()
            else:
                await session.flush()

            return result.rowcount
        except SQLAlchemyError as e:
            raise DatabaseException(
                f"Error updating {self.model.__name__} with filters {filters}: {str(e)}"
            ) from e

    async def update_by_conditions(
        self,
        session: AsyncSession,
        conditions: list[SQLColumnExpression],
        updates: dict,
        commit_self: bool = True,
    ) -> int:
        """
        Asynchronously updates records in the database that match the given conditions with the provided updates.
        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session to use for the update operation.
            conditions (list[SQLColumnExpression]): A list of SQLAlchemy expressions to filter the records to update.
            updates (dict): A dictionary containing the fields and their new values to update in the records.
            commit_self (bool, optional): If True, commits the transaction after the update; otherwise, flushes the session. Defaults to True.
        Returns:
            int: The number of records updated.
        Raises:
            DatabaseException: If an error occurs while updating the records or committing the transaction.
        """
        try:
            stmt: Update = (
                sa_update(self.model).where(and_(*conditions)).values(**updates)
            )
            result = await session.execute(stmt)

            if commit_self:
                await session.commit()
            else:
                await session.flush()

            return result.rowcount
        except SQLAlchemyError as e:
            raise DatabaseException(
                f"Error updating {self.model.__name__} with conditions {conditions}: {str(e)}"
            ) from e

    async def delete(
        self, session: AsyncSession, id: UUID, commit_self: bool = True
    ) -> bool:
        """
        Asynchronously deletes a record from the database by its UUID.
        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session to use for the operation.
            id (UUID): The unique identifier of the record to delete.
            commit_self (bool, optional): If True, commits the transaction after deletion;
                if False, only flushes the session. Defaults to True.
        Returns:
            bool: True if the deletion operation was executed.
        Raises:
            DatabaseException: If an error occurs while deleting the record or committing the transaction.
        """
        try:
            stmt: Delete = sa_delete(self.model).where(self.model.id == id)
            await session.execute(stmt)

            if commit_self:
                await session.commit()
            else:
                await session.flush()

            return True
        except (SQLAlchemyError, ValueError) as e:
            raise DatabaseException(
                f"Error deleting {self.model.__name__} with ID {id}: {str(e)}"
            ) from e

    async def delete_by_filters(
        self, session: AsyncSession, filters: dict, commit_self: bool = True
    ) -> int:
        """
        Asynchronously deletes records from the database that match the given filters.
        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session to use for the delete operation.
            filters (dict): A dictionary of filter conditions to identify the records to delete.
            commit_self (bool, optional): If True, commits the transaction after the delete; otherwise, flushes the session. Defaults to True.
        Returns:
            int: The number of records deleted.
        Raises:
            DatabaseException: If an error occurs while deleting the records or committing the transaction.
        """
        try:
            stmt: Delete = sa_delete(self.model).where(
                and_(*[getattr(self.model, k) == v for k, v in filters.items()])
            )
            result = await session.execute(stmt)

            if commit_self:
                await session.commit()
            else:
                await session.flush()

            return result.rowcount
        except SQLAlchemyError as e:
            raise DatabaseException(
                f"Error deleting {self.model.__name__} with filters {filters}: {str(e)}"
            ) from e

    async def get_or_create(
        self,
        session: AsyncSession,
        defaults: dict,
        filters: dict,
        commit_self: bool = True,
    ) -> tuple[T, bool]:
        """
        Retrieves an instance of the model matching the given filters from the database.
        If no such instance exists, creates a new one with the combined filters and defaults.
        Args:
            session (AsyncSession): The asynchronous database session to use for the query and creation.
            defaults (dict): A dictionary of default values to use when creating a new instance.
            filters (dict): A dictionary of filter conditions to locate an existing instance.
            commit_self (bool, optional): Whether to commit the session after creation. Defaults to True.
        Returns:
            tuple[T, bool]: A tuple containing the model instance and a boolean indicating whether it was created (True) or retrieved (False).
        Raises:
            DatabaseException: If an error occurs while querying or creating the instance.
        """
        try:
            stmt = select(self.model).filter_by(**filters)
            result = await session.execute(stmt)
            instance = result.scalar_one_or_none()

            if instance:
                return instance, False

            return (
                await self.create(
                    session, {**filters, **defaults}, commit_self=commit_self
                ),
                True,
            )
        except (SQLAlchemyError, ValueError) as e:
            raise DatabaseException(
                f"Error getting or creating {self.model.__name__}: {str(e)}"
            ) from e

    async def exists(self, session: AsyncSession, filters: dict) -> bool:
        """
        Checks if an instance of the model exists in the database that matches the given filters.
        Args:
            session (AsyncSession): The asynchronous database session to use for the query.
            filters (dict): A dictionary of filter conditions to apply to the query.
        Returns:
            bool: True if an instance exists, False otherwise.
        Raises:
            DatabaseException: If an error occurs while querying the database.
        """
        try:
            stmt = select(self.model).filter_by(**filters)
            result = await session.execute(stmt)
            return result.scalars().first() is not None
        except (SQLAlchemyError, ValueError) as e:
            raise DatabaseException(
                f"Error checking existence of {self.model.__name__} with filters {filters}: {str(e)}"
            ) from e

    async def soft_delete(
        self, session: AsyncSession, id: UUID, commit_self: bool = True
    ) -> T | None:
        """
        Asynchronously soft-deletes a record by setting is_deleted=True and deleted_at timestamp.

        This method does not remove the record from the database; it marks it as deleted
        by setting the `is_deleted` flag to True and recording the deletion timestamp.

        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session to use for the operation.
            id (UUID): The unique identifier of the record to soft-delete.
            commit_self (bool, optional): If True, commits the transaction after the update;
                if False, only flushes the session. Defaults to True.

        Returns:
            T | None: The soft-deleted record as an instance of the model, or None if no record
                was found with the given ID.

        Raises:
            DatabaseException: If an error occurs while updating the record or committing the transaction.
        """
        from datetime import datetime, timezone

        try:
            now = datetime.now(timezone.utc)
            stmt: Update = (
                sa_update(self.model)
                .where(self.model.id == id)
                .values(is_deleted=True, deleted_at=now, updated_at=now)
                .returning(self.model)
            )
            result = await session.execute(stmt)

            if commit_self:
                await session.commit()
            else:
                await session.flush()

            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                f"Error soft-deleting {self.model.__name__} with ID {id}: {str(e)}"
            ) from e

    async def soft_delete_by_filters(
        self, session: AsyncSession, filters: dict, commit_self: bool = True
    ) -> int:
        """
        Asynchronously soft-deletes records that match the given filters.

        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session to use for the operation.
            filters (dict): A dictionary of filter conditions to identify the records to soft-delete.
            commit_self (bool, optional): If True, commits the transaction after the update;
                if False, only flushes the session. Defaults to True.

        Returns:
            int: The number of records soft-deleted.

        Raises:
            DatabaseException: If an error occurs while updating the records or committing the transaction.
        """
        from datetime import datetime, timezone

        try:
            now = datetime.now(timezone.utc)
            stmt: Update = (
                sa_update(self.model)
                .where(and_(*[getattr(self.model, k) == v for k, v in filters.items()]))
                .values(is_deleted=True, deleted_at=now, updated_at=now)
            )
            result = await session.execute(stmt)

            if commit_self:
                await session.commit()
            else:
                await session.flush()

            return result.rowcount
        except SQLAlchemyError as e:
            raise DatabaseException(
                f"Error soft-deleting {self.model.__name__} with filters {filters}: {str(e)}"
            ) from e

    async def soft_delete_by_conditions(
        self,
        session: AsyncSession,
        conditions: list[SQLColumnExpression],
        commit_self: bool = True,
    ) -> int:
        """
        Asynchronously soft-deletes records that match the given conditions.

        Args:
            session (AsyncSession): The SQLAlchemy asynchronous session to use for the operation.
            conditions (list[SQLColumnExpression]): A list of SQLAlchemy expressions to filter
                the records to soft-delete.
            commit_self (bool, optional): If True, commits the transaction after the update;
                if False, only flushes the session. Defaults to True.

        Returns:
            int: The number of records soft-deleted.

        Raises:
            DatabaseException: If an error occurs while updating the records or committing the transaction.
        """
        from datetime import datetime, timezone

        try:
            now = datetime.now(timezone.utc)
            stmt: Update = (
                sa_update(self.model)
                .where(and_(*conditions))
                .values(is_deleted=True, deleted_at=now, updated_at=now)
            )
            result = await session.execute(stmt)

            if commit_self:
                await session.commit()
            else:
                await session.flush()

            return result.rowcount
        except SQLAlchemyError as e:
            raise DatabaseException(
                f"Error soft-deleting {self.model.__name__} with conditions {conditions}: {str(e)}"
            ) from e
