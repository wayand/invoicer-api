# Invoicer API

The Invoicer API is the backend service for managing invoice operations within the invoicer.wayand.dk platform. It provides a range of functionalities to support invoice generation, user management, and financial transactions.

## Project Overview

This backend service is designed to handle all server-side operations related to invoicing and user management. It exposes RESTful API endpoints for client applications like the invoicer-vue frontend to interact with.

## Technical Stack

- **Framework**: Flask (Python)
- **Database**: PostgreSQL
- **ORM**: SQLAlchemy
- **Authentication**: JWT and OAuth 2.0
- **API Documentation**: Swagger/OpenAPI

## Features

- User Authentication and Authorization
- Invoice Creation and Management
- Customer and Vendor Management
- Payment Processing
- Reporting and Analytics

## Installation Instructions

To set up the API locally:

1. Clone the repository:
   ```bash
   git clone https://github.com/wayand/invoicer-api.git
   cd invoicer-api
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install package dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up the environment variables:
   - Copy `.env.example` to `.env` and fill in your configuration:
   ```env
   FLASK_APP=app.py
   FLASK_ENV=development
   DATABASE_URL=postgresql://username:password@localhost:5432/invoicer_db
   SECRET_KEY=your-secret-key
   ```

5. Initialize the database:
   ```bash
   flask db upgrade
   ```

6. Start the Flask development server:
   ```bash
   flask run
   ```

## API Endpoints

1. **User Management**
   - `POST /api/v1/users/register`: Register a new user
   - `POST /api/v1/users/login`: Login user and retrieve JWT

2. **Invoice Operations**
   - `GET /api/v1/invoices`: List all invoices
   - `POST /api/v1/invoices`: Create a new invoice

3. **Client Operations**
   - `GET /api/v1/clients`: List all clients
   - `POST /api/v1/clients`: Add new client

## Deployment

To deploy this API in a production environment, consider using:
- Gunicorn as the WSGI server
- Nginx as a reverse proxy
- Docker for containerization (Dockerfile included)

Example Gunicorn deployment:
```bash
gunicorn --bind 0.0.0.0:5000 wsgi:app
```

Configure Nginx to forward requests to your Gunicorn server.

## Contributing

Contributions are welcome! To contribute to this project:
1. Fork the repository
2. Create a new feature branch
3. Submit a pull request

## License

This project is licensed under the MIT License. See the LICENSE file for more details.

# Invoicer API
All endpoints for the invoicer application.

## # invoicer-api