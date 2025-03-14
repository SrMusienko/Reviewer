import uvicorn
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from services import ReviewFetcher, ReviewAnalyzer
from logger_config import logger


templates = Jinja2Templates(directory="templates")

app = FastAPI(title="Product Review Analyzer")
app.mount("/static", StaticFiles(directory="static"), name="static")



# Model for request
class ProductQuery(BaseModel):
    query: str


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Main page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/analyze")
async def analyze(query: ProductQuery, background_tasks: BackgroundTasks):
    """API endpoint for product analysis"""
    try:
        product_name = query.query.strip()
        logger.info(f"Analyzing product: {product_name}")

        # Step 1: Search for product reviews
        my_reviewer_fetcher = ReviewFetcher(product_name)
        my_reviewer_fetcher.search_google(num_results=4)  # Limiting to 3 for faster results
        
        # Step 2: Extract page content
        sites_content, site_names = await my_reviewer_fetcher.extract_multiple_pages()
        logger.info(f"Found {len(sites_content)} sites with reviews")

        # Step 3: Analyze the content
        my_review_analyzer = ReviewAnalyzer(product_name, sites_content, site_names)
        product_info = my_review_analyzer.analyze_product()
        
        # Step 4: Generate a summary
        summary = my_review_analyzer.generate_summary()
        
        product_info_dict = product_info.as_dict()
        print(f'product_info_dict->{product_info_dict}')
        
        # Step 5: Return the results

        return {
            "success": True, 
            "product_info": product_info.as_dict(),
            "summary": summary
        }
    except Exception as e:
        logger.error(f"Error analyzing product: {e}")
        return {"success": False, "error": str(e)}
    
    # Запуск приложения
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)