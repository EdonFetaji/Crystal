import asyncio
from celery import shared_task
from backend.management.commands.upload_stock_data import main

@shared_task
def run_stock_update():
    """
    Celery task to run the stock update asynchronously.
    """
    asyncio.run(main())


@shared_task
def test_task():
    return "Test Task Executed"
