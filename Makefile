# Makefile for FastMCP Server

.PHONY: install run test coverage clean status

# Install dependencies
install:
	uv pip install -r requirements.txt
	uv pip install -r requirements-dev.txt
	uv

# Run the FastMCP server
run:
	python3.11 -m src.PROJECT_NAME

# deploy
deploy:
	pm2 deploy ecosystem.config.js production

# Run tests
test:
	python3.11 -m pytest tests/

# Run tests with coverage
coverage:
	python3.11 -m pytest --cov=src tests/

# Clean up __pycache__ directories
clean:
	find . -name "__pycache__" -exec rm -r {} +

# Check status of submodules and remote PM2 processes
status:
	git submodule foreach "git status"
	ssh eaws "pm2 ls"
	ssh saws "pm2 ls"
