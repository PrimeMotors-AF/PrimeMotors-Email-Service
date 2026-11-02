
from fastapi import FastAPI
from src.routes.emailRoutes import router as email_router

app = FastAPI(
    title="Prime Motors Email Service",
    description="Microserviço responsável pelo envio de e-mails do Prime Motors.",
    version="1.0.0",
)

app.include_router(email_router)
