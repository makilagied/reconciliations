# Exit on any error
$ErrorActionPreference = "Stop"



#Tag the Docker image
Write-Host "Building the Docker image..."
docker build -t itrust-recons-sit .

# Tag the Docker image
Write-Host "Tagging the Docker image..."
docker tag itrust-recons-sit:latest itrust.registryuat:10000/itrust-recons-sit:latest

#  Push the Docker image to the registry
Write-Host "Pushing the Docker image to the registry..."
docker push itrust.registryuat:10000/itrust-recons-sit:latest

Write-Host "Build and push process completed successfully."

# powershell -ExecutionPolicy Bypass -File deploy.ps1
