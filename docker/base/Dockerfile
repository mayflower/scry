# Base image with Python, Playwright and browsers
FROM mcr.microsoft.com/playwright/python:v1.43.0-jammy

# Set workdir
WORKDIR /app

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Create artifacts dir (mounted in compose)
RUN mkdir -p /app/artifacts

