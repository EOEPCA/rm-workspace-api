# build is docker-compose build
all:
	docker-compose run --user 0 workspace-api bash -c "pytest && flake8 && mypy ."

build:
	docker-compose build

test:
	docker-compose run workspace-api pytest -s

test-watch:
	docker-compose run workspace-api ptw

lint:
	docker-compose run --user 0 workspace-api bash -c "flake8 && mypy ."

lint-watch:
	docker-compose run --user 0 workspace-api bash -c "watch -n1  bash -c \"flake8 && mypy .\""
	
upgrade-packages:
	docker-compose run --user 0 workspace-api bash -c "python3 -m pip install pip-upgrader && pip-upgrade --skip-package-installation"

bash:
	docker-compose run --user `id -u` workspace-api bash
