import json
import os
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = "uek_project_secret_key"
OUTPUT_DIR = "extracted_products"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1
class Opinion:
    def __init__(self, data_dict):
        self.opinion_id = data_dict.get("opinion_id", "")
        self.author = data_dict.get("author", "")
        self.recommendation = data_dict.get("recommendation", "No recommendation")
        self.stars = data_dict.get("stars", "")
        self.content = data_dict.get("content", "")
        self.advantages = data_dict.get("advantages", [])
        self.disadvantages = data_dict.get("disadvantages", [])
        self.helpful = data_dict.get("helpful", "0")
        self.unhelpful = data_dict.get("unhelpful", "0")
        self.publish_date = data_dict.get("publish_date", "")
        self.purchase_date = data_dict.get("purchase_date", "")


class Product:
    def __init__(self, product_id, opinions_list):
        self.product_id = product_id
        self.opinions = [Opinion(op) for op in opinions_list]
        self.total_opinions = len(self.opinions)
        self.opinions_with_advantages = sum(1 for op in self.opinions if op.advantages)
        self.opinions_with_disadvantages = sum(1 for op in self.opinions if op.disadvantages)
        self.average_score = self._calculate_average()

    def _calculate_average(self):
        total_score = 0.0
        valid_count = 0
        for op in self.opinions:
            if op.stars:
                try:
                    score_str = op.stars.split("/")[0].replace(",", ".")
                    total_score += float(score_str)
                    valid_count += 1
                except ValueError:
                    pass
        return round(total_score / valid_count, 2) if valid_count > 0 else 0.0


def extract_opinions_from_page(soup, extracted_opinions):
    opinions = soup.select("div.user-post__card[data-entry-id]")
    
    for opinion in opinions:
        opinion_id = opinion.get("data-entry-id", "")
        
        author_tag = opinion.select_one("span.user-post__author-name")
        author = author_tag.text.strip() if author_tag else ""
        
        recommendation_tag = opinion.select_one("span.user-post__author-recomendation")
        recommendation = recommendation_tag.text.strip() if recommendation_tag else "No recommendation"
        
        stars_tag = opinion.select_one("span.user-post__score-count")
        stars = stars_tag.text.strip() if stars_tag else ""
        
        content_tag = opinion.select_one("div.user-post__text")
        content = content_tag.text.strip() if content_tag else ""
        
        advantages = [tag.text.strip() for tag in opinion.select(".review-feature__title--positives ~ .review-feature__item")]
        disadvantages = [tag.text.strip() for tag in opinion.select(".review-feature__title--negatives ~ .review-feature__item")]

        helpful_tag = opinion.select_one("button.vote-yes span")
        helpful = helpful_tag.text.strip() if helpful_tag else "0"
        
        unhelpful_tag = opinion.select_one("button.vote-no span")
        unhelpful = unhelpful_tag.text.strip() if unhelpful_tag else "0"
        
        time_tags = opinion.select("span.user-post__published time")
        publish_date = time_tags[0].get("datetime", "") if len(time_tags) >= 1 else ""
        purchase_date = time_tags[1].get("datetime", "") if len(time_tags) >= 2 else ""

        opinion_data = {
            "opinion_id": opinion_id, "author": author, "recommendation": recommendation,
            "stars": stars, "content": content, "advantages": advantages,
            "disadvantages": disadvantages, "helpful": helpful, "unhelpful": unhelpful,
            "publish_date": publish_date, "purchase_date": purchase_date
        }
        extracted_opinions.append(opinion_data)


def scrape_all_product_reviews(product_id):
    base_url = f"https://www.ceneo.pl/{product_id}"
    current_url = f"{base_url}#tab=reviews"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    all_opinions = []
    
    while current_url:
        response = requests.get(current_url, headers=headers)
        if response.status_code != 200:
            break
            
        soup = BeautifulSoup(response.text, "html.parser")
        extract_opinions_from_page(soup, all_opinions)
        
        next_page_tag = soup.select_one("a.pagination__next")
        if next_page_tag and next_page_tag.get("href"):
            current_url = "https://www.ceneo.pl" + next_page_tag.get("href")
        else:
            current_url = None
            
    return all_opinions


def generate_product_charts(product):
    static_charts_dir = os.path.join("static", "charts")
    os.makedirs(static_charts_dir, exist_ok=True)

    rec_counts = {}
    for op in product.opinions:
        rec_counts[op.recommendation] = rec_counts.get(op.recommendation, 0) + 1
        
    plt.figure(figsize=(5, 5))
    plt.pie(rec_counts.values(), labels=rec_counts.keys(), autopct='%1.1f%%', startangle=140, colors=['#4CAF50', '#FF5722', '#9E9E9E'])
    plt.title("Recommendations Ratio")
    plt.savefig(os.path.join(static_charts_dir, f"{product.product_id}_pie.png"))
    plt.close()

    star_categories = ["1/5", "1,5/5", "2/5", "2,5/5", "3/5", "3,5/5", "4/5", "4,5/5", "5/5"]
    star_counts = {cat: 0 for cat in star_categories}
    for op in product.opinions:
        if op.stars in star_counts:
            star_counts[op.stars] += 1
            
    plt.figure(figsize=(7, 4))
    plt.bar(star_counts.keys(), star_counts.values(), color='#2196F3')
    plt.title("Score Distribution Tracker")
    plt.tight_layout()
    plt.savefig(os.path.join(static_charts_dir, f"{product.product_id}_bar.png"))
    plt.close()


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/extract", methods=["GET", "POST"])
def extract():
    if request.method == "POST":
        pid = request.form.get("product_id", "").strip()
        if not pid:
            flash("Product ID cannot be left blank!", "error")
            return redirect(url_for("extract"))
            
        raw_data = scrape_all_product_reviews(pid)
        if not raw_data:
            flash("Invalid Code or no reviews found on Ceneo properties.", "error")
            return redirect(url_for("extract"))
            
        with open(os.path.join(OUTPUT_DIR, f"{pid}.json"), "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=4)
            
        return redirect(url_for("product_view", product_id=pid))
        
    return render_template("extract.html")


@app.route("/products")
def products_list():
    files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".json")]
    all_products = []
    
    for filename in files:
        pid = filename.replace(".json", "")
        with open(os.path.join(OUTPUT_DIR, filename), "r", encoding="utf-8") as f:
            data = json.load(f)
            all_products.append(Product(pid, data))
            
    return render_template("products.html", products=all_products)


@app.route("/product/<product_id>")
def product_view(product_id):
    filepath = os.path.join(OUTPUT_DIR, f"{product_id}.json")
    if not os.path.exists(filepath):
        flash("Target item database record not located locally.", "error")
        return redirect(url_for("products_list"))
        
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    product = Product(product_id, data)
    generate_product_charts(product)
    return render_template("product_view.html", product=product)


@app.route("/download/<product_id>")
def download_file(product_id):
    return send_from_directory(OUTPUT_DIR, f"{product_id}.json", as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)