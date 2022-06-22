docker-compose down
docker-compose build --force-rm
docker-compose up -d
docker logs discord_bot --follow