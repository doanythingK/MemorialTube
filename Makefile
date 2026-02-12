LOCAL_COMPOSE=docker compose -f docker-compose.local.yml

.PHONY: up down logs ps api worker

up:
	$(LOCAL_COMPOSE) up --build -d

down:
	$(LOCAL_COMPOSE) down

logs:
	$(LOCAL_COMPOSE) logs -f --tail=200

ps:
	$(LOCAL_COMPOSE) ps

api:
	$(LOCAL_COMPOSE) logs -f --tail=200 api

worker:
	$(LOCAL_COMPOSE) logs -f --tail=200 worker
