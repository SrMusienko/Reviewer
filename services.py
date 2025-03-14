import asyncio
import re

from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from googlesearch import search
from llama_cpp import Llama
from playwright.async_api import async_playwright

from logger_config import logger

class ReviewFetcher:
    """Class for searching and cleaning information"""
    def __init__(self, query: str):
        self._found_prod_name = query.strip()
        self._links = []
        self._site_names = []  # Added to store site names
        self._additional_links = set()

    def search_google(self, num_results: int = 5) -> list[str]:
        """Searches links through DuckDuckGo and Google"""
        try:
            ddg_results = DDGS().text("ukraine "+self._found_prod_name, max_results=num_results)
            for result in ddg_results:
                self._links.append(result.get("href"))
                # Extract site name from URL
                site_name = self._extract_site_name(result.get("href"))
                self._site_names.append(site_name)
            
        except Exception as e:
            logger.error(f"Error during DuckDuckGo search: {e}")
            
        try:    
            if len(self._links) < num_results:
                google_links = list(search("review users "+self._found_prod_name, num_results=num_results))
                for link in google_links:
                    if link not in self._links:
                        self._links.append(link)
                        site_name = self._extract_site_name(link)
                        self._site_names.append(site_name)
        except Exception as e:
            logger.error(f"Error during Google search: {e}")
            
        # Limit to the required number
        self._links = self._links[:num_results]
        self._site_names = self._site_names[:num_results]
        return self._links
    
    def _extract_site_name(self, url: str) -> str:
        """Extract readable site name from URL"""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            # Remove www. if present and get the main domain
            site_name = domain.replace('www.', '').split('.')[0]
            return site_name.capitalize()
        except Exception:
            return "Unknown Site"

    async def extract_multiple_pages(self) -> tuple[list[str], list[str]]:
        """Extract content from pages and return both content and site names"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)  # Changed to headless=True for production
            page = await browser.new_page()
            # Log browser errors
            page.on("console", lambda msg: print(f"Browser Console: {msg.text}"))
            page.on("pageerror", lambda error: print(f"Page Error: {error}"))
            results = []
            site_names = []
            
            for i, url in enumerate(self._links):
                clear_content = ""
                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    # Scroll page to load lazy content
                    await page.evaluate("""
                        window.scrollTo({
                            top: document.body.scrollHeight,
                            behavior: 'smooth'
                        });
                    """)
                    await asyncio.sleep(2)
                    content = await page.content()
                    clear_content = await self.clear_information(content)
                    results.append(clear_content[:3000])  # Increased limit for better context
                    site_names.append(self._site_names[i] if i < len(self._site_names) else self._extract_site_name(url))
                except Exception as e:
                    logger.error(f"Error loading {url}: {e}")
                    results.append("")
                    site_names.append("Error Site")
            await browser.close()
            return results, site_names
        
    async def clear_information(self, content: str, chunk_size=480) -> str:
        soup = BeautifulSoup(content, 'html.parser')
        
        # Save page title
        title = soup.title.get_text() if soup.title else "No title"
        
        # Remove all scripts, styles and other unnecessary elements
        for tag in soup.find_all(['script', 'style', 'iframe', 'noscript', 'svg', 'canvas']):
            tag.decompose()  # Changed to decompose for better cleanup
        
        # Replace some tags with their text equivalents while preserving structure
        for br in soup.find_all('br'):
            br.replace_with('\n')
        
        for hr in soup.find_all('hr'):
            hr.replace_with('\n---\n')
        
        # Process headings
        for i in range(1, 7):
            for h in soup.find_all(f'h{i}'):
                h_text = h.get_text(strip=True)
                h.replace_with(BeautifulSoup(f"\n{'#' * i} {h_text}\n", 'html.parser'))
        
        # Process paragraphs
        for p in soup.find_all('p'):
            p_text = p.get_text(strip=True)
            p.replace_with(BeautifulSoup(f"\n{p_text}\n", 'html.parser'))
        
        # Process lists
        for ul in soup.find_all('ul'):
            new_content = "\n"
            for li in ul.find_all('li', recursive=False):
                new_content += f"* {li.get_text(strip=True)}\n"
            ul.replace_with(BeautifulSoup(new_content, 'html.parser'))
        
        for ol in soup.find_all('ol'):
            new_content = "\n"
            for i, li in enumerate(ol.find_all('li', recursive=False), 1):
                new_content += f"{i}. {li.get_text(strip=True)}\n"
            ol.replace_with(BeautifulSoup(new_content, 'html.parser'))
        
        # Process tables (simplified)
        for table in soup.find_all('table'):
            new_content = "\n<TABLE>\n"
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['th', 'td'])
                row_content = " | ".join([cell.get_text(strip=True) for cell in cells])
                new_content += f"{row_content}\n"
            new_content += "</TABLE>\n"
            table.replace_with(BeautifulSoup(new_content, 'html.parser'))
        
        # Process links
        for a in soup.find_all('a'):
            if a.get('href') and a.get_text(strip=True):
                a.replace_with(BeautifulSoup(f"[{a.get_text(strip=True)}]({a.get('href')})", 'html.parser'))
        
        # Process images
        for img in soup.find_all('img'):
            alt_text = img.get('alt', 'image')
            src = img.get('src', '')
            img.replace_with(BeautifulSoup(f"![{alt_text}]({src})", 'html.parser'))
        
        # Get cleaned text
        cleaned_text = soup.get_text(separator='\n', strip=True)
        
        # Clean text from multiple line breaks and spaces
        cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
        cleaned_text = re.sub(r' {2,}', ' ', cleaned_text)
        
        # Add page title at the beginning
        full_text = f"# {title}\n\n{cleaned_text}"
        
        return full_text


class ProductDescription:
    def __init__(self):
        self.site_names = []
        self.ratings = []
        self.pros = []
        self.cons = []
        self.similar_products = {}
        
    def calculate_average_rating(self):
        """Calculate average rating from all numerical ratings"""
        valid_ratings = []
        for rating in self.ratings:
            try:
                # Try to extract numeric values with regex
                match = re.search(r'(\d+(\.\d+)?)', rating)
                if match:
                    valid_ratings.append(float(match.group(1)))
            except (ValueError, AttributeError):
                continue
                
        if not valid_ratings:
            return None
        return sum(valid_ratings) / len(valid_ratings)
    
    def as_dict(self):
        """Return data as dictionary for easier access in templates"""
        result = []
        for i in range(len(self.site_names)):
            site_data = {
                "site_name": self.site_names[i] if i < len(self.site_names) else "Unknown",
                "rating": self.ratings[i] if i < len(self.ratings) else "No data",
                "pros": self.pros[i] if i < len(self.pros) else "No data",
                "cons": self.cons[i] if i < len(self.cons) else "No data"
            }
            result.append(site_data)
        return result
    
class ReviewAnalyzer:
    """Class for analyzing product review information"""
    def __init__(self, query: str, sites_content: list[str], site_names: list[str]):
        self._found_prod_name = query.strip()
        self._lock = asyncio.Lock()
        self._description = ProductDescription()
        self.sites_content = sites_content
        self.site_names = site_names
        self._description.site_names = site_names

    def analyze_product(self) -> ProductDescription:
        """Analyzes product information from multiple sites"""
        


        for num, content in enumerate(self.sites_content, start=1):
            if not content.strip():
                self._description.ratings.append("No data")
                self._description.pros.append("No data")
                self._description.cons.append("No data")
                continue

            try:
                llm = Llama(
                    model_path="../models/gemma-2-2b-it.Q8_0.gguf",
                    n_ctx=16384,
                    )
                # Extract rating
                content_multiline = content.split('\n')
                prompt = (
                f"<QUESTION>:You are an expert in analyzing product reviews. "
                f"Extract only the rating of '{self._found_prod_name}' from the information below. "
                f"If the rating is missing or does not match the product, return 'no data'"
                f"Answer format If a rating is found: 'Rating: X.X'\n"
                f"Be concise and specific. Don't add explanations."
                f"<CONTENT INFORMATION>: <<\n{content_multiline}\n>>"
                )
                
                response = llm(
                    prompt,
                    max_tokens=250,
                    temperature=0.1,
                    top_p=0.1,
                    stop=["<QUESTION>", "<CONTENT INFORMATION>"])
                rating = re.sub(r'^Rating:\s*', '', response["choices"][0]["text"].strip())

                self._description.ratings.append(rating)
                llm.reset()
                # Extract pros
                prompt = (
                f"<QUESTION>:You are an expert in analyzing product reviews. "
                f"Extract only the PROS of '{self._found_prod_name}' from the content below. "
                f"If the needed information is missing or does not match the product, return 'no data'"
                f"Be concise and specific. Don't add explanations.\n\n"
                f"<CONTENT INFORMATION>: <<\n{content_multiline}\n>>"
                )
                response = llm(
                    prompt,
                    max_tokens=250,
                    temperature=0.7,
                    top_p=0.3,
                    stop=["<QUESTION>", "<CONTENT INFORMATION>"]
                )
                result = response["choices"][0]["text"].strip()
                llm.reset()
                # Make sure the result has proper bullet points
                if not result.startswith("*"):
                    lines = result.split("\n")
                    result = "\n".join([f"* {line.strip('- ')}" for line in lines if line.strip()])
                pros = result
                self._description.pros.append(pros)
                # Extract cons
                prompt = (
                f"<QUESTION>:You are an expert in analyzing product reviews. "
                f"Extract only the CONS of '{self._found_prod_name}' from the content below. "
                f"If the needed information is missing or does not match the product, return 'no data'"
                f"Be concise and specific. Don't add explanations.\n\n"
                f"<CONTENT INFORMATION>:<<\n{content_multiline}\n>>"
                )
                response = llm(
                    prompt,
                    max_tokens=250,
                    temperature=0.7,
                    top_p=0.3,
                    stop=["<QUESTION>", "<CONTENT INFORMATION>"]
                )
                result = response["choices"][0]["text"].strip()
                # Make sure the result has proper bullet points
                if not result.startswith("*"):
                    lines = result.split("\n")
                    result = "\n".join([f"* {line.strip('- ')}" for line in lines if line.strip()])
                cons = result
                self._description.cons.append(cons)
            finally:
                llm.reset()
                llm.close()
            
            print(f"Site {self.site_names[num-1]} analysis:")
            print(f"Rating: {rating}")
            print(f"Pros: {pros}")
            print(f"Cons: {cons}")
            print("-" * 40)
            
        return self._description
    
    def _extract_rating(self, content: str, num: int) -> str:
        """Extract product rating from content"""
        prompt = (
            f"<QUESTION>:You are an expert in analyzing product reviews. "
            f"Extract only the rating of '{self._found_prod_name}' from the information below. "
            f"If the rating is missing or does not match the product, return 'no data'"
            f"Answer format If a rating is found: 'Rating: X.X'\n"
            f"Be concise and specific. Don't add explanations."
            f"<CONTENT INFORMATION>: <<\n{content}\n>>"
        )
    
        self._llm.reset()
        response = self._llm(
            prompt,
            max_tokens=50,
            temperature=0.1,
            top_p=0.1,
            stop=["<QUESTION>", "<CONTENT INFORMATION>"]
        )
        result = response["choices"][0]["text"].strip()
        # Clean up common issues in responses
        result = re.sub(r'^Rating:\s*', '', result)
    
        return result
    
    def _extract_pros(self, content: str, num: int) -> str:
        """Extract product pros from content"""

        prompt = (
            f"<QUESTION>:You are an expert in analyzing product reviews. "
            f"Extract only the PROS of '{self._found_prod_name}' from the content below. "
            f"If the needed information is missing or does not match the product, return 'no data'"
            f"Be concise and specific. Don't add explanations.\n\n"
            f"<CONTENT INFORMATION>: <<\n{content}\n>>"
        )
        self._llm.reset()
        response = self._llm(
            prompt,
            max_tokens=250,
            temperature=0.1,
            top_p=0.1,
            stop=None
        )
        result = response["choices"][0]["text"].strip()
        if not result or "no" in result.lower() and "found" in result.lower():
            return "No advantages found"
        self._llm.reset()
    # Make sure the result has proper bullet points
        if not result.startswith("*"):
            lines = result.split("\n")
            result = "\n".join([f"* {line.strip('- ')}" for line in lines if line.strip()])
        
        return result
    
    def _extract_cons(self, content: str, num: int) -> str:
        """Extract product cons from content"""
        prompt = (
            f"<QUESTION>:You are an expert in analyzing product reviews. "
            f"Extract only the CONS of '{self._found_prod_name}' from the content below. "
            f"If the needed information is missing or does not match the product, return 'no data'"
            f"Be concise and specific. Don't add explanations.\n\n"
            f"<CONTENT INFORMATION>:<<\n{content}\n>>"
        )
        self._llm.reset()
    
        response = self._llm(
            prompt,
            max_tokens=250,
            temperature=0.1,
            top_p=0.1,
            stop=None
        )
        result = response["choices"][0]["text"].strip()
        if not result or "no" in result.lower() and "found" in result.lower():
            return "No disadvantages found"
        
    # Make sure the result has proper bullet points
        if not result.startswith("*"):
            lines = result.split("\n")
            result = "\n".join([f"* {line.strip('- ')}" for line in lines if line.strip()])
        
        return result
    
    def generate_summary(self) -> str:
        """Generate a summary of all findings"""
        avg_rating = self._description.calculate_average_rating()
        rating_text = f"{avg_rating:.1f}/10" if avg_rating else "Unknown"
        
        # Build a markdown table for all sites
        table = "# Product Analysis Summary for " + self._found_prod_name + "\n\n"
        table += f"**Average Rating:** {rating_text}\n\n"
        table += "## Detailed Analysis by Source\n\n"
        table += "| Site | Rating | Pros | Cons |\n"
        table += "|------|--------|------|------|\n"
        
        for i in range(len(self._description.site_names)):
            site = self._description.site_names[i]
            rating = self._description.ratings[i].replace("\n", " ")
            
            # Format pros and cons for table
            pros = self._description.pros[i].replace("\n", "<br>").replace("* ", "✓ ")
            cons = self._description.cons[i].replace("\n", "<br>").replace("* ", "✗ ")
            
            table += f"| {site} | {rating} | {pros} | {cons} |\n"
        
        # Add a conclusion section
        table += "\n## Conclusion\n\n"
        
        conclusion_prompt = (
            f"Based on the following product analysis for '{self._found_prod_name}', write a 3-4 sentence conclusion. "
            f"Average Rating: {rating_text}\n"
        )
        
        # Add some pros and cons to the conclusion prompt
        all_pros = []
        all_cons = []
        for i in range(len(self._description.pros)):
            if "No " not in self._description.pros[i]:
                pros_lines = self._description.pros[i].split("\n")
                all_pros.extend([line.strip("* ") for line in pros_lines if line.strip()])
            
            if "No " not in self._description.cons[i]:
                cons_lines = self._description.cons[i].split("\n")
                all_cons.extend([line.strip("* ") for line in cons_lines if line.strip()])
        
        # Take the top 5 most mentioned pros and cons
        conclusion_prompt += "Pros:\n"
        for pro in all_pros[:5]:
            conclusion_prompt += f"- {pro}\n"
            
        conclusion_prompt += "Cons:\n"
        for con in all_cons[:5]:
            conclusion_prompt += f"- {con}\n"
        
        conclusion_response = self._llm(
            conclusion_prompt,
            max_tokens=250,
            temperature=0.7,
            top_p=0.5
        )
        
        conclusion = conclusion_response["choices"][0]["text"].strip()
        table += conclusion
        
        return table