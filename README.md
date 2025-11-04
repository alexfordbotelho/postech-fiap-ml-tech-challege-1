# API Tech Challenger

This project is an API built with FastAPI that provides machine learning, asynchronous web scraping, and JWT authentication functionalities, with complete monitoring using Prometheus, Grafana, and Loki.

## Diagrama da Arquitetura

```mermaid
graph TD
    Client[Cliente] -->|Request| API[API FastAPI]
    API -->|Authentication| JWT[JWT Auth]
    
    JWT[JWT Auth] --> MongoDB[(MongoDB)]
    API --> |Get Books| Books[Books]
    Books[Books] --> MongoDB[(MongoDB)]

    API -->|Web Scraping Assíncrono| WS[Scraper]
    WS[Scraper] --> MongoDB[(MongoDB)]
    
    API -->|ML Predictions| ML[Machine Learning]
    ML[Machine Learning] --> MongoDB[(MongoDB)]

    MongoDB[(MongoDB)] --> API

    API -->|Logs| Loki[Loki]
    Promtail -->|Coleta Logs| Loki
    Loki --> Grafana[Grafana]
    API -->|Métricas| Prometheus[Prometheus]
    Prometheus --> Grafana

    style API fill:#005571
    style MongoDB fill:#4ea94b
    style Prometheus fill:#E6522C
    style Grafana fill:#F46800
    style Loki fill:#F9B716
```

## 📁 Project Structure

```bash
api-tech-challenger/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Main application
│   ├── auth.py                    # JWT authentication system
│   ├── middleware.py              # Middlewares (Logging, Auth)
│   ├── machine_learning.py        # ML models and predictions
│   ├── webscrapper.py             # Async web scraping
│   └── requirements.txt           # Python dependencies
├── observability/
│   ├── grafana/
│   │   └── provisioning/          # Pre-configured dashboards
│   ├── loki/
│   │   └── loki-config.yml        # Loki configuration
│   └── promtail/
│       └── promtail-config.yml    # Promtail configuration
├── prometheus/
│   └── prometheus.yml             # Prometheus configuration
├── terraform/                      # Infrastructure as code
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── test/
│   └── test_api.py                # Automated tests
├── docker-compose.yml              # Container orchestration
├── Dockerfile.yml                  # API Docker image
├── .env.example                    # Environment variables template
└── README.md                       # This file
```

### Prerequisites

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **Git**
- **Terraform** 1.0+ (optional, for infrastructure provisioning)
- **Python** 3.12+ (for local development only)


### 1️⃣ Clone the Repository

```bash
git clone <repository-url>
cd api-tech-challenger
```

### 2️⃣ Configure Environment Variables

```bash
cp .env.example .env
```

Edit the `.env` file with your own credentials and configuration:

```env
# MongoDB
USER_MONGODB=admin
PASS_MONGODB=your_secure_password
DATABASE_NAME=app_db
COLLECTION_NAME=books

# Ports
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
LOKI_PORT=3100
```

### 3️⃣ Start the Containers

```bash
docker compose up -d
```

### 4️⃣ Check Status

```bash
docker compose ps
```

You should see all services with "Up" status:
```
NAME                IMAGE                              STATUS
api                 app-api-tech-challenger            Up
mongodb             mongodb/mongodb-community-server   Up
prometheus          prom/prometheus:v2.55.1            Up
grafana             grafana/grafana:11.2.0             Up
loki                grafana/loki:3.1.1                 Up
promtail            grafana/promtail:3.1.1             Up
```

Once started, the API will be available at `http://localhost:8081`

### 5️⃣ Access the Application

- **API**: http://localhost:8081
- **Interactive Documentation**: http://localhost:8081/docs
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus Metrics**: http://localhost:8081/metrics

---

## Endpoints da API

### Authentication

- **POST** `/api/v1/auth/register`
  - Registers a new user
  - Body: 
    ```json
    {
        "username": "string",
        "email": "string",
        "password": "string",
        "full_name": "string"
    }
    ```

- **POST** `/api/v1/auth/login`
  - Authenticates a user and returns a JWT token
  - Body:
    ```json
    {
        "username": "string",
        "password": "string"
    }
    ```

### Books

- **GET** `/api/v1/books`
  - Retrieves a paginated list of all books
  - Query Parameters:
    - `page`: page number
    - `limit`: number of items per page
    - `catalog`: filter by category
    - `min_price`: prminimum price
    - `max_price`: maximum price

- **GET** `/api/v1/books/{id}`
  - Retrieves details for a specific book

- **GET** `/api/v1/categories/`
  - Returns all registered categories

- **GET** `/api/v1/stats/categories/`
  - Returns category statistics including
    - Category name
    - Total number of books
    - Average price
    - Minimum and maximum prices
    - Total stock

### Statistics

- **GET** `/api/v1/books/stats/overview`
  - Returns general book statistics
    - Total books
    - Average prices
    - Total categories
    - Distribution by category
    - Price ranges

- **GET** `/api/v1/health`
    - Checks API and database connection status.
    - Returns basic system metrics.

### Web Scraping (Assíncrono)

- **POST** `/api/v1/scrapping`
    - Starts an asynchronous web scraping job.
    - Requires JWT Authentication
    - Uses aiohttp for async requests
    - Processes multiple pages concurrently
    - Supports configurable concurrency limits
    - Body:
        ```json
        {
            "max_concurrent": 10,
            "categories": ["Travel", "Mystery", "Historical Fiction"]
        }
        ```

### Machine Learning

- **GET** `/api/v1/ml/features`
    - Performs predictions using the trained model.
    - Requires JWT Authentication.
    - Body:
        ```json
        [
          {
            "name": "string",
            "original_name": "string",
            "dtype": "float",
            "min": 0,
            "max": 0,
            "mean": 0,
            "std": 0
          }
        ]
        ```

- **GET** `/api/v1/ml/training-data`
    - Returns metadata about the current ML model
    - Body
        ```json
          [
            {
              "name": "string",
              "original_name": "string",
              "dtype": "float",
              "min": 0,
              "max": 0,
              "mean": 0,
              "std": 0
            }
          ]
        ```

## Testes

To run API tests:

```bash
# No ambiente local
python3 test/test_api.py

# Ou dentro do container
docker compose exec api-tech-challenger python3 test/test_api.py
```

Test coverage includes:
    - User registration
    - Authentication
    - Protected routes

## Monitoramento

### Prometheus
- Access metrics at: `http://localhost:9090`
- Collects metrics from API and MongoDB

### Grafana
- Dashboard: `http://localhost:3000`
- Default credentials: admin/admin
- Pre-configured dashboards for:
  - API metrics
  - MongoDB performance
  - Application logs

  **Useful queries:**

  ```logql
  # All API logs
  {service="api-tech-challenger"}

  # Only errors
  {service="api-tech-challenger"} |= "ERROR"

  # Logs from a specific user
  {service="api-tech-challenger"} | json | user="john"

  # Slow requests (>1s)
  {service="api-tech-challenger"} | json | duration > 1
  ```

### Loki
- Endpoint: `http://localhost:3100`
- Centralized log aggregation
- Integrated with Promtail for log collection
- View logs via Grafana
- Collects:
  - API logs
  - MongoDB logs
  - Web Scraping logs
  - Machine Learning logs

## Terraform Structure

```bash
terraform/
├── main.tf              # Main resources
├── variables.tf         # Input variables
├── outputs.tf           # Outputs (IPs, URLs)
├── provider.tf          # Provider configuration
└── terraform.tfvars     # Variable values
```

### Provisioning

#### 1️⃣ Initialize Terraform

```bash
cd terraform
terraform init
```

#### 2️⃣ Configure Variables

Edit `terraform.tfvars`:

```hcl
# General settings
project_name = "api-tech-challenger"
environment  = "production"
region       = "us-east-1"

# Network
vpc_cidr = "10.0.0.0/16"

# Compute
instance_type = "t3.medium"
instance_count = 2

# MongoDB
mongodb_instance_type = "t3.small"
mongodb_storage_size  = 50

# Tags
tags = {
  Project     = "API Tech Challenger"
  Environment = "Production"
  ManagedBy   = "Terraform"
}
```

#### 3️⃣ Plan Changes

```bash
terraform plan
```

#### 4️⃣ Apply Infrastructure

```bash
terraform apply
```

Type `yes` when prompted.

#### 5️⃣ Outputs

After applying, Terraform will display:

```
Outputs:

api_endpoint = "http://api-tech-challenger-lb-123456.us-east-1.elb.amazonaws.com"
prometheus_url = "http://prometheus-123456.us-east-1.elb.amazonaws.com:9090"
grafana_url = "http://grafana-123456.us-east-1.elb.amazonaws.com:3000"
mongodb_connection_string = "mongodb://admin:***@mongodb-instance:27017"
```

### 6️⃣ Run into Cloud

```bash
gcloud compute ssh postech-fiap-ml-tech-challenge-1-instance --zone=us-central1-a

cd /opt/app
```

Edit the `.env` file with your own credentials and configuration:

```env
# MongoDB
USER_MONGODB=admin
PASS_MONGODB=your_secure_password
DATABASE_NAME=app_db
COLLECTION_NAME=books

# Ports
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
LOKI_PORT=3100
```
Start container

```bash
docker compose up -d
```



## Stack Tecnológica

- **Backend**: FastAPI
- **Database**: MongoDB
- **Machine Learning**: scikit-learn
- **Web Scraping**: aiohttp + BeautifulSoup4
- **Authentication**: JWT
- **Containerization**: Docker
- **Observability**: 
  - Prometheus (Metrics)
  - Grafana (Dashboard)
  - Loki + Promtail (Logs)
- **Terraform**