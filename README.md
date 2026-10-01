# ShopMate E-Commerce Concierge

ShopMate is a full-stack, multi-agent AI concierge built for e-commerce. It uses LangGraph to orchestrate complex user requests—from product discovery and cart management to order tracking and customer support—all through a natural language interface.

**Live Environment:**
- **Frontend Live Demo:** [https://shopmate-ecommerce-concierge.vercel.app/](https://shopmate-ecommerce-concierge.vercel.app/)
- **Backend API URL:** [https://shopmate-ecommerce-concierge.onrender.com](https://shopmate-ecommerce-concierge.onrender.com)

## Architecture

The project consists of a FastAPI backend and a React/Vite frontend.

### Backend (`/app`)
- **Framework:** FastAPI
- **AI/LLM:** LangChain, LangGraph, Google GenAI (Gemini)
- **Vector Search:** FAISS & Sentence Transformers
- **Database:** SQLite (handles products, orders, carts, sessions, price history)
- **Security & Rate Limiting:** JWT, bcrypt, SlowAPI

### Frontend (`/frontend`)
- **Framework:** React 19 + Vite
- **Styling:** TailwindCSS 4, Framer Motion
- **Markdown Rendering:** react-markdown

## Features

- **Multi-Agent Orchestration:** Uses a supervisor agent pattern to route requests to specialized agents (e.g., Catalog, Cart, Order, Support).
- **Conversational Commerce:** Users can ask for product recommendations, add items to the cart, apply coupons, and checkout using natural language.
- **Order Management:** Real-time mock tracking for orders, delivery estimates, and complaint handling.
- **Long-term Memory:** Stores user preferences, default shipping addresses, and interaction history.
- **Price History & Deals:** Tracks price drops and applies active coupon codes automatically.

## Local Development

### Prerequisites
- Python 3.10+
- Node.js 18+

### Backend Setup

1. Clone the repository.
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables in the root directory (create a `.env` file):
   ```ini
   # Required
   GEMINI_API_KEY=your_gemini_api_key

   # Optional (for tracing)
   LANGCHAIN_TRACING_V2=true
   LANGCHAIN_API_KEY=your_langsmith_key
   LANGCHAIN_PROJECT=shopmate

   # Security
   JWT_SECRET=your_jwt_secret
   CORS_ORIGINS=http://localhost:5173
   ```

4. Start the FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```
   The backend will run at `http://localhost:8000`. The SQLite database will be initialized automatically in the `data/` folder on the first run.

### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install Node dependencies:
   ```bash
   npm install
   ```

3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   The frontend will run at `http://localhost:5173`.

## License

MIT
