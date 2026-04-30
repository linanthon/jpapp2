from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from app.config import (TASKIQ_BROKER_URL, TASKIQ_CONSUMER_GROUP, TASKIQ_MAX_WORKERS,
                        TASKIQ_QUEUE_NAME, TASKIQ_RESULT_URL, TASKIQ_STREAM_MAXLEN_MAIN)


broker = RedisStreamBroker(
    url=TASKIQ_BROKER_URL,
    queue_name=TASKIQ_QUEUE_NAME,
    consumer_group_name=TASKIQ_CONSUMER_GROUP,
    max_connection_pool_size=max(TASKIQ_MAX_WORKERS, 2),
    maxlen=max(TASKIQ_STREAM_MAXLEN_MAIN, 1),
).with_result_backend(
    RedisAsyncResultBackend(redis_url=TASKIQ_RESULT_URL)
)
