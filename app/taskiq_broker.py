from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.config import TASKIQ_BROKER_URL, TASKIQ_RESULT_URL


broker = ListQueueBroker(url=TASKIQ_BROKER_URL).with_result_backend(
    RedisAsyncResultBackend(redis_url=TASKIQ_RESULT_URL)
)
