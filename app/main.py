from fastapi import FastAPI, HTTPException, Query, Path, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Dict, Any, Annotated
from datetime import datetime, timedelta
from bson import ObjectId
from pydantic.json_schema import JsonSchemaValue
from sklearn.linear_model import LogisticRegression
from sklearn.datasets import load_iris
import numpy as np
from dotenv import load_dotenv
from typing import List, Literal, Dict, Union
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema
from app.webscrapper import main_async
from app.machine_learning import (
    FeatureInfo,
    IrisFeatures,
    IrisFeaturesList,
    PredictionItem,
    PredictionResponse,
    TrainingRow,
    softmax_logits_proba
)

import os
from contextlib import asynccontextmanager
import re

# Importar módulos de autenticação e logging
from app.auth import (
    get_current_user, 
    get_password_hash, 
    verify_password, 
    create_access_token,
    UserCreate, 
    UserLogin, 
    UserInDB, 
    Token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

from app.middleware import LoggingMiddleware, AuthContextMiddleware, global_db

load_dotenv()

# Custom PyObjectId for Pydantic v2
class PyObjectId(str):
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler: GetCoreSchemaHandler):
        def validate(v):
            if isinstance(v, ObjectId):
                return v
            if isinstance(v, str) and ObjectId.is_valid(v):
                return ObjectId(v)
            raise ValueError("Invalid ObjectId")

        python_schema = core_schema.union_schema([
            core_schema.is_instance_schema(ObjectId),
            core_schema.str_schema(),
        ])

        python_schema = core_schema.no_info_after_validator_function(validate, python_schema)

        serializer = core_schema.plain_serializer_function_ser_schema(
            lambda v: str(v), when_used="always"
        )

        json_schema = core_schema.str_schema()

        return core_schema.json_or_python_schema(
            json_schema=json_schema,
            python_schema=python_schema,
            serialization=serializer,
        )

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: Dict[str, Any], handler: Any) -> JsonSchemaValue:
        schema['type'] = 'string'
        return schema


class BookDetails(BaseModel):
    title: str
    description: str
    upc: str
    product_type: str
    price_excl_tax: str
    price_incl_tax: str
    tax: str
    availability: str
    number_of_reviews: str

    @field_validator('price_excl_tax', 'price_incl_tax', 'tax', mode='before')
    @classmethod
    def clean_price(cls, v):
        if isinstance(v, str):
            return v.replace('£', '').replace('$', '').replace(',', '')
        return v


class BookModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
        json_schema_extra={
            "example": {
                "catalog": "Travel",
                "image": "https://books.toscrape.com/media/cache/27/a5/27a53d0bb95bdd88288eaf66c9230d7e.jpg",
                "title": "It's Only the Himalayas",
                "price": "£45.17",
                "detail_url": "https://books.toscrape.com/catalogue/its-only-the-himalayas_981/index.html",
                "details": {
                    "title": "It's Only the Himalayas",
                    "description": "Wherever you go, whatever you do, just . . . don't do anything stupid.",
                    "upc": "a22124811bfa8350",
                    "product_type": "Books",
                    "price_excl_tax": "£45.17",
                    "price_incl_tax": "£45.17",
                    "tax": "£0.00",
                    "availability": "In stock (19 available)",
                    "number_of_reviews": "0"
                }
            }
        }
    )

    id: Annotated[Optional[PyObjectId], Field(alias="_id")] = None
    catalog: str = Field(..., description="Category/Catalog of the book")
    image: Optional[str] = Field(None, description="URL of book cover image")
    title: str = Field(..., min_length=1)
    price: str = Field(..., description="Price as string with currency")
    detail_url: Optional[str] = Field(None, description="URL for book details")
    details: Optional[BookDetails] = None


class BookResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., alias="_id")
    catalog: str
    image: Optional[str] = None
    title: str
    price: str
    price_numeric: Optional[float] = None
    detail_url: Optional[str] = None
    details: Optional[BookDetails] = None
    rating: Optional[float] = None
    stock: Optional[int] = None

    @field_validator('price_numeric', mode='after')
    @classmethod
    def calculate_price_numeric(cls, v, info):
        if 'price' in info.data:
            price_str = info.data['price']
            price_clean = re.sub(r'[^\d.,]', '', price_str)
            price_clean = price_clean.replace(',', '')
            try:
                return float(price_clean)
            except:
                return 0.0
        return v

    @field_validator('stock', mode='after')
    @classmethod
    def extract_stock(cls, v, info):
        if 'details' in info.data and info.data['details']:
            details = info.data['details']
            if isinstance(details, dict) and 'availability' in details:
                availability = details['availability']
            elif hasattr(details, 'availability'):
                availability = details.availability
            else:
                return 0
            match = re.search(r'\((\d+)\s+available\)', availability)
            if match:
                return int(match.group(1))
            elif 'In stock' in availability:
                return 1
        return 0

    @field_validator('rating', mode='after')
    @classmethod
    def extract_rating(cls, v):
        return None


class CategoryStats(BaseModel):
    category: str
    total_books: int
    average_price: float
    min_price: float
    max_price: float
    total_in_stock: int


class OverviewStats(BaseModel):
    total_books: int
    average_price: float
    total_categories: int
    total_in_stock: int
    price_ranges: dict
    categories_distribution: dict


class HealthResponse(BaseModel):
    status: str
    database: str
    timestamp: datetime
    books_count: int
    collections: List[str]


# Database connection
MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

client: AsyncIOMotorClient = None
db = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global client, db
    print("🚀 INICIANDO LIFESPAN...")
    
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    
    print(f"✅ Conectado ao MongoDB: {MONGODB_URL}")
    print(f"   Database: {DATABASE_NAME}")

    # Create indexes
    await db[COLLECTION_NAME].create_index("title")
    await db[COLLECTION_NAME].create_index("catalog")
    await db[COLLECTION_NAME].create_index("price")
    
    # Create index for users collection
    await db["users"].create_index("username", unique=True)
    await db["users"].create_index("email", unique=True)
    
    # Create indexes for logs collection
    await db["request_logs"].create_index("timestamp")
    await db["request_logs"].create_index("user")
    await db["request_logs"].create_index("is_authenticated")
    
    print("✅ Índices criados")
    
    # Inicializar o middleware de logging com o banco de dados
    global_db = db
    print(f"✅ MongoDB configurado para middleware: {db.name}")
    print(f"   Collections disponíveis: {await db.list_collection_names()}")
    print(f"   global_db configurado: {global_db is not None}")

    yield

    # Shutdown
    print("🛑 ENCERRANDO LIFESPAN...")
    client.close()


# Initialize FastAPI
app = FastAPI(
    title="Books API",
    description="API para gerenciamento de livros com autenticação JWT e logging",
    version="1.0.0",
    lifespan=lifespan
)


@app.on_event("startup")
async def startup_event():
    """
    Evento de startup - alternativa/backup ao lifespan
    Este sempre executa, mesmo em versões antigas do FastAPI
    """
    global client, db
    
    print("=" * 80)
    print("🚀 STARTUP EVENT EXECUTADO")
    print("=" * 80)
    
    if db is None:
        print("⚠️  Database ainda não inicializado pelo lifespan, inicializando agora...")
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]
        
        print(f"✅ Conectado ao MongoDB: {MONGODB_URL}")
        print(f"   Database: {DATABASE_NAME}")
        
        # Create indexes
        await db[COLLECTION_NAME].create_index("title")
        await db[COLLECTION_NAME].create_index("catalog")
        await db[COLLECTION_NAME].create_index("price")
        await db["users"].create_index("username", unique=True)
        await db["users"].create_index("email", unique=True)
        await db["request_logs"].create_index("timestamp")
        await db["request_logs"].create_index("user")
        await db["request_logs"].create_index("is_authenticated")
        
        print("✅ Índices criados")
    
    # SEMPRE configurar o middleware (mesmo que lifespan já tenha executado)
    global_db = db
    
    print(f"✅ MongoDB CONFIGURADO para middleware!")
    print(f"   Database name: {db.name}")
    print(f"   Collections: {await db.list_collection_names()}")
    print(f"   middleware.global_db is None: {global_db is None}")
    print("=" * 80)
    print("🎉 APLICAÇÃO PRONTA PARA RECEBER REQUISIÇÕES")
    print("=" * 80)


@app.on_event("shutdown")
async def shutdown_event():
    """Evento de shutdown"""
    global client
    print("🛑 ENCERRANDO APLICAÇÃO...")
    if client:
        client.close()
        print("✅ Conexão com MongoDB fechada")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Adicionar middlewares de autenticação e logging
# IMPORTANTE: A ordem importa! AuthContextMiddleware deve vir antes do LoggingMiddleware
app.add_middleware(AuthContextMiddleware)
app.add_middleware(LoggingMiddleware)


# ============== ROTAS DE AUTENTICAÇÃO (PÚBLICAS) ==============

@app.post("/api/v1/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED, tags=['Authentication'])
async def register(user: UserCreate):
    """
    Registrar novo usuário
    Rota pública - não requer autenticação
    """
    # Verificar se usuário já existe
    existing_user = await db["users"].find_one({"username": user.username})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username já está em uso"
        )
    
    # Verificar se email já existe
    existing_email = await db["users"].find_one({"email": user.email})
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já está em uso"
        )
    
    # Criar novo usuário
    user_dict = {
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "hashed_password": get_password_hash(user.password),
        "created_at": datetime.utcnow(),
        "is_active": True
    }
    
    await db["users"].insert_one(user_dict)
    
    # Criar token de acesso
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/api/v1/auth/login", response_model=Token, tags=['Authentication'])
async def login(user_login: UserLogin):
    """
    Login de usuário
    Rota pública - não requer autenticação
    """
    # Buscar usuário
    user = await db["users"].find_one({"username": user_login.username})
    
    if not user or not verify_password(user_login.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário inativo"
        )
    
    # Criar token de acesso
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


# ============== ROTAS PROTEGIDAS (REQUEREM AUTENTICAÇÃO) ==============

@app.get("/api/v1/health", response_model=HealthResponse, tags=['Statistics'])
async def health_check(current_user: str = Depends(get_current_user)):
    """
    Health check endpoint - PROTEGIDO
    Requer autenticação JWT
    """
    try:
        books_count = await db[COLLECTION_NAME].count_documents({})
        collections = await db.list_collection_names()

        return HealthResponse(
            status="healthy",
            database=DATABASE_NAME,
            timestamp=datetime.utcnow(),
            books_count=books_count,
            collections=collections
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/books", response_model=Dict[str, Any], tags=['Books'])
async def get_books(
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    catalog: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    search: Optional[str] = None,
    in_stock: Optional[bool] = None,
    current_user: str = Depends(get_current_user)
):
    """
    Listar livros com paginação e filtros - PROTEGIDO
    Requer autenticação JWT
    """
    try:
        skip = (page - 1) * limit
        
        query_filter = {}
        
        if catalog:
            query_filter["catalog"] = {"$regex": catalog, "$options": "i"}
        
        if search:
            query_filter["title"] = {"$regex": search, "$options": "i"}
        
        if in_stock is not None:
            if in_stock:
                query_filter["details.availability"] = {"$regex": "In stock", "$options": "i"}
            else:
                query_filter["details.availability"] = {"$not": {"$regex": "In stock", "$options": "i"}}
        
        if min_price is not None or max_price is not None:
            query_filter["$expr"] = {}
            price_conditions = []
            
            if min_price is not None:
                price_conditions.append({
                    "$gte": [
                        {
                            "$toDouble": {
                                "$replaceAll": {
                                    "input": {
                                        "$replaceAll": {
                                            "input": "$price",
                                            "find": "£",
                                            "replacement": ""
                                        }
                                    },
                                    "find": ",",
                                    "replacement": ""
                                }
                            }
                        },
                        min_price
                    ]
                })
            
            if max_price is not None:
                price_conditions.append({
                    "$lte": [
                        {
                            "$toDouble": {
                                "$replaceAll": {
                                    "input": {
                                        "$replaceAll": {
                                            "input": "$price",
                                            "find": "£",
                                            "replacement": ""
                                        }
                                    },
                                    "find": ",",
                                    "replacement": ""
                                }
                            }
                        },
                        max_price
                    ]
                })
            
            query_filter["$expr"] = {"$and": price_conditions} if len(price_conditions) > 1 else price_conditions[0]
        
        total_items = await db[COLLECTION_NAME].count_documents(query_filter)
        
        cursor = db[COLLECTION_NAME].find(query_filter).skip(skip).limit(limit)
        books = await cursor.to_list(length=limit)
        
        book_responses = []
        for book in books:
            book["_id"] = str(book["_id"])
            book_responses.append(BookResponse(**book))
        
        total_pages = (total_items + limit - 1) // limit
        
        return {
            "items": book_responses,
            "total": total_items,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/books/{book_id}", response_model=BookResponse, tags=['Books'])
async def get_book(
    book_id: Annotated[str, Path(description="Book ID")],
    current_user: str = Depends(get_current_user)
):
    """
    Obter detalhes de um livro específico - PROTEGIDO
    Requer autenticação JWT
    """
    try:
        if not ObjectId.is_valid(book_id):
            raise HTTPException(status_code=400, detail="ID inválido")
        
        book = await db[COLLECTION_NAME].find_one({"_id": ObjectId(book_id)})
        
        if not book:
            raise HTTPException(status_code=404, detail="Livro não encontrado")
        
        book["_id"] = str(book["_id"])
        return BookResponse(**book)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/categories", response_model=List[str], tags=['Books'])
async def get_all_categories(current_user: str = Depends(get_current_user)):
    """
    Lista todas as categorias - PROTEGIDO
    Requer autenticação JWT
    """
    try:
        categories = await db[COLLECTION_NAME].distinct("catalog")
        return sorted([cat for cat in categories if cat])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats/overview", response_model=OverviewStats, tags=['Statistics'])
async def get_overview_stats(current_user: str = Depends(get_current_user)):
    """
    Estatísticas gerais - PROTEGIDO
    Requer autenticação JWT
    """
    try:
        pipeline = [
            {
                "$facet": {
                    "total": [{"$count": "count"}],
                    "categories": [{"$group": {"_id": "$catalog"}}, {"$count": "count"}],
                    "priceStats": [
                        {
                            "$addFields": {
                                "price_numeric": {
                                    "$toDouble": {
                                        "$replaceAll": {
                                            "input": {
                                                "$replaceAll": {
                                                    "input": {"$ifNull": ["$price", "0"]},
                                                    "find": "£",
                                                    "replacement": ""
                                                }
                                            },
                                            "find": ",",
                                            "replacement": ""
                                        }
                                    }
                                }
                            }
                        },
                        {
                            "$group": {
                                "_id": None,
                                "avg": {"$avg": "$price_numeric"}
                            }
                        }
                    ],
                    "priceDist": [
                        {
                            "$addFields": {
                                "price_numeric": {
                                    "$toDouble": {
                                        "$replaceAll": {
                                            "input": {
                                                "$replaceAll": {
                                                    "input": {"$ifNull": ["$price", "0"]},
                                                    "find": "£",
                                                    "replacement": ""
                                                }
                                            },
                                            "find": ",",
                                            "replacement": ""
                                        }
                                    }
                                }
                            }
                        },
                        {
                            "$bucket": {
                                "groupBy": "$price_numeric",
                                "boundaries": [0, 10, 25, 50, 100, 200, 500, 1000],
                                "default": "1000+",
                                "output": {"count": {"$sum": 1}}
                            }
                        }
                    ],
                    "categoryDist": [
                        {
                            "$group": {
                                "_id": "$catalog",
                                "count": {"$sum": 1}
                            }
                        },
                        {"$sort": {"count": -1}},
                        {"$limit": 10}
                    ],
                    "inStock": [
                        {
                            "$match": {
                                "details.availability": {"$regex": "In stock", "$options": "i"}
                            }
                        },
                        {"$count": "count"}
                    ]
                }
            }
        ]

        result = await db[COLLECTION_NAME].aggregate(pipeline).to_list(1)

        if not result or not result[0]["total"]:
            return OverviewStats(
                total_books=0,
                average_price=0,
                total_categories=0,
                total_in_stock=0,
                price_ranges={},
                categories_distribution={}
            )

        stats_data = result[0]

        price_dist = {}
        boundaries = [0, 10, 25, 50, 100, 200, 500, 1000]
        for item in stats_data.get("priceDist", []):
            if item["_id"] == "1000+":
                price_dist["£1000+"] = item["count"]
            else:
                idx = boundaries.index(item["_id"])
                if idx < len(boundaries) - 1:
                    price_dist[f"£{item['_id']}-£{boundaries[idx + 1]}"] = item["count"]

        cat_dist = {}
        for item in stats_data.get("categoryDist", []):
            if item["_id"]:
                cat_dist[item["_id"]] = item["count"]

        return OverviewStats(
            total_books=stats_data["total"][0]["count"] if stats_data["total"] else 0,
            average_price=round(stats_data["priceStats"][0]["avg"], 2) if stats_data["priceStats"] and
                                                                          stats_data["priceStats"][0] else 0,
            total_categories=stats_data["categories"][0]["count"] if stats_data["categories"] else 0,
            total_in_stock=stats_data["inStock"][0]["count"] if stats_data["inStock"] else 0,
            price_ranges=price_dist,
            categories_distribution=cat_dist
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats/categories", response_model=List[CategoryStats], tags=['Books'])
async def get_category_stats(current_user: str = Depends(get_current_user)):
    """
    Estatísticas por categoria - PROTEGIDO
    Requer autenticação JWT
    """
    try:
        pipeline = [
            {
                "$addFields": {
                    "price_numeric": {
                        "$toDouble": {
                            "$replaceAll": {
                                "input": {
                                    "$replaceAll": {
                                        "input": {"$ifNull": ["$price", "0"]},
                                        "find": "£",
                                        "replacement": ""
                                    }
                                },
                                "find": ",",
                                "replacement": ""
                            }
                        }
                    },
                    "in_stock": {
                        "$cond": {
                            "if": {
                                "$regexMatch": {
                                    "input": {"$ifNull": ["$details.availability", ""]},
                                    "regex": "In stock"
                                }
                            },
                            "then": 1,
                            "else": 0
                        }
                    }
                }
            },
            {
                "$group": {
                    "_id": "$catalog",
                    "total_books": {"$sum": 1},
                    "avg_price": {"$avg": "$price_numeric"},
                    "min_price": {"$min": "$price_numeric"},
                    "max_price": {"$max": "$price_numeric"},
                    "total_in_stock": {"$sum": "$in_stock"}
                }
            },
            {
                "$match": {
                    "_id": {"$ne": None}
                }
            },
            {
                "$sort": {"total_books": -1}
            }
        ]

        result = await db[COLLECTION_NAME].aggregate(pipeline).to_list(None)

        return [
            CategoryStats(
                category=item["_id"],
                total_books=item["total_books"],
                average_price=round(item["avg_price"], 2) if item["avg_price"] else 0,
                min_price=round(item["min_price"], 2) if item["min_price"] else 0,
                max_price=round(item["max_price"], 2) if item["max_price"] else 0,
                total_in_stock=item["total_in_stock"]
            )
            for item in result
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post('/api/v1/auth/scrapping', status_code=status.HTTP_201_CREATED, tags=['Processing'])
async def scrapping_endpoint(current_user: str = Depends(get_current_user)):
    """
    Endpoint de scrapping - PROTEGIDO
    Requer autenticação JWT
    """

    result = await main_async()
    return {'code': 200, 'message': 'Scrapping completed successfully'}


# ============== ROTAS DE LOGS (ADMIN) ==============

@app.get("/api/v1/logs", tags=['Statistics'])
async def get_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    is_authenticated: Optional[bool] = None,
    user: Optional[str] = None,
    current_user: str = Depends(get_current_user)
):
    """
    Consultar logs da aplicação - PROTEGIDO
    Requer autenticação JWT
    """
    try:
        skip = (page - 1) * limit
        
        query_filter = {}
        if is_authenticated is not None:
            query_filter["is_authenticated"] = is_authenticated
        if user:
            query_filter["user"] = user
        
        total = await db["request_logs"].count_documents(query_filter)
        
        logs = await db["request_logs"].find(query_filter)\
            .sort("timestamp", -1)\
            .skip(skip)\
            .limit(limit)\
            .to_list(length=limit)
        
        # Converter ObjectId para string
        for log in logs:
            log["_id"] = str(log["_id"])
        
        return {
            "items": logs,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

# ============== ROTAS DE MACHINE LEARNING  ==============

# ====== Carrega dados e treina modelo na inicialização ======
iris = load_iris(as_frame=True)
sk_cols = iris.feature_names  # ['sepal length (cm)', 'sepal width (cm)', ...]
target_names = iris.target_names.tolist()  # ['setosa', 'versicolor', 'virginica']

# Mapeia nomes do sklearn -> API snake_case
api_cols = ["sepal_length", "sepal_width", "petal_length", "petal_width"]
col_map = dict(zip(sk_cols, api_cols))
rev_col_map = {v: k for k, v in col_map.items()}

df = iris.frame.rename(columns=col_map)  # renomeia para snake_case
X = df[api_cols].copy()
y = iris.target

model = LogisticRegression(max_iter=200, multi_class="auto", n_jobs=None)
model.fit(X.values, y)

MODEL_META = {
    "name": "iris-logreg",
    "version": "1",
    "classes": target_names,
    "features": api_cols,
}

@app.get("/api/v1/ml/features", response_model=List[FeatureInfo], tags=['Machine Learning'])
def get_features(current_user: str = Depends(get_current_user)):

    out: List[FeatureInfo] = []
    for api_name in api_cols:
        s = df[api_name]
        out.append(FeatureInfo(
            name=api_name,
            original_name=rev_col_map[api_name],
            dtype="float",
            min=float(s.min()),
            max=float(s.max()),
            mean=float(s.mean()),
            std=float(s.std()),
        ))
    return out

@app.get("/api/v1/ml/training-data", response_model=List[TrainingRow], tags=['Machine Learning'])
def get_training_data(
    limit: int = Query(50, ge=1, le=150),
    offset: int = Query(0, ge=0, le=149),
    include_target: bool = Query(True, description="Inclui colunas de alvo"),
    current_user: str = Depends(get_current_user)
):
    end = min(offset + limit, len(df))
    subset = df.iloc[offset:end].copy()
    y_subset = y[offset:end]

    rows: List[TrainingRow] = []
    for i, row in subset.iterrows():
        item = TrainingRow(
            sepal_length=float(row.sepal_length),
            sepal_width=float(row.sepal_width),
            petal_length=float(row.petal_length),
            petal_width=float(row.petal_width),
        )
        if include_target:
            item.target = int(y_subset.loc[i])
            item.target_label = target_names[item.target]
        rows.append(item)
    return rows

@app.post("/api/v1/ml/predictions", response_model=PredictionResponse, tags=['Machine Learning'])
def post_predictions(payload: Union[IrisFeatures, IrisFeaturesList], current_user: str = Depends(get_current_user)):
    # Normaliza para lista
    if isinstance(payload, IrisFeatures):
        items = [payload]
    else:
        items = payload.root

    X_in = np.array([[it.sepal_length, it.sepal_width, it.petal_length, it.petal_width] for it in items], dtype=float)
    preds = model.predict(X_in)
    probs = model.predict_proba(X_in)

    results: List[PredictionItem] = []
    for idx, (c, p) in enumerate(zip(preds, probs)):
        results.append(
            PredictionItem(
                index=idx,
                predicted_class=int(c),
                predicted_label=target_names[int(c)],
                probabilities=softmax_logits_proba(p, target_names),
            )
        )
    return PredictionResponse(
        model_name=MODEL_META["name"],
        model_version=MODEL_META["version"],
        results=results,
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)