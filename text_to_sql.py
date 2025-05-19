import json
import re
import warnings

# LangChain uyarılarını filtrele
warnings.filterwarnings("ignore", category=UserWarning, module="langchain")

import streamlit as st
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM
from sqlalchemy import create_engine, inspect

db_url = "sqlite:///Northwind_small.sqlite"

template = """
Sen bir SQL sorgu oluşturucususun. Northwind veritabanı şeması ve kullanıcının Türkçe sorusu verildiğinde, SQLite uyumlu bir SQL sorgusu oluştur. 
SADECE SQL ifadesini döndür, başka hiçbir şey yazma. Açıklama gerekmez.

ÖNEMLİ TABLO VE ALAN İSİMLERİ (BUNLARI KULLAN):
- Customer: Müşteri bilgileri (Id, CompanyName, ContactName, City, Country, vb.)
- Order: Sipariş bilgileri (Id, OrderDate, CustomerId, ShipCity, ShipCountry, vb.)
- OrderItem: Sipariş detayları (Id, OrderId, ProductId, Quantity, UnitPrice)
- Product: Ürün bilgileri (Id, ProductName, SupplierId, CategoryId, UnitPrice, UnitsInStock)
- Category: Kategori bilgileri (Id, CategoryName, Description)
- Employee: Çalışan bilgileri (Id, FirstName, LastName, Title, City, Country)
- Supplier: Tedarikçi bilgileri (Id, CompanyName, ContactName, City, Country, vb.)

DİKKAT:
- Tablo isimleri TEKİL olarak kullanılmalıdır (Products değil Product, Categories değil Category gibi)
- Alan isimleri büyük harfle başlamalıdır (Örn: ProductName, UnitPrice)
- JOIN yaparken doğru alan isimlerini kullan (Örn: Product.CategoryId = Category.Id)

Veritabanı şeması: {schema}
Kullanıcı sorusu: {query}
Çıktı (SADECE SQL):
"""

try:
    # Gemma3 4B modelini kullanıyoruz
    model = OllamaLLM(
        model="gemma3:4b",
        base_url="http://127.0.0.1:11434",
        temperature=0.1,     # Düşük sıcaklık daha tutarlı yanıtlar için
        top_p=0.9,          # Daha hızlı yanıt için
        top_k=40,           # Daha iyi çeşitlilik için
        num_ctx=2048,       # Bağlam penceresi
        num_thread=4,       # CPU thread sayısı
        request_timeout=30.0 # Zaman aşımı
    )
    # Bağlantıyı test et
    model.invoke("test")
except Exception as e:
    print(f"Ollama bağlantı hatası: {e}")
    print("Lütfen Ollama'nın çalıştığından emin olun: 'ollama serve'")
    import sys
    sys.exit(1)

# Veritabanı bağlantısını önbelleğe al
@st.cache_resource
def get_db_engine():
    return create_engine(db_url)

def extract_schema(db_url):
    engine = get_db_engine()
    inspector = inspect(engine)
    schema = {}

    for table in inspector.get_table_names():
        columns = inspector.get_columns(table)
        schema[table] = [col['name'] for col in columns]

    return json.dumps(schema)

@st.cache_data(ttl=300)  # 5 dakika süreyle önbellekte tut
def to_sql_query(query, schema):
    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | model
    
    # Daha kısa yanıtlar için max_tokens sınırı ekle
    response = chain.invoke({
        "query": query, 
        "schema": schema
    }, config={"max_tokens": 500})
    
    return clean_text(response)

def clean_text(text: str):
    # Markdown kod bloklarını temizle
    text = re.sub(r'```(?:sql)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text, flags=re.IGNORECASE)
    
    # Diğer temizlik işlemleri
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    
    # Eğer hala SQL ifadesi içeriyorsa sadece SQL kısmını al
    sql_match = re.search(r'(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE).*', text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        text = sql_match.group(0)
    
    return text.strip()

schema = extract_schema(db_url)
st.title("Metinden SQL Sorgu Oluşturucu")

# Metin alanı ve gönder butonu
query = st.text_area(
    "Veritabanından çekmek istediğiniz veriyi Türkçe olarak yazın:",
    help="Sorgunuzu yazdıktan sonra göndermek için 'Sorguyu Çalıştır' butonuna tıklayın. Alt satıra geçmek için Ctrl+Enter kullanın.",
    key="query_input"
)

# Sorguyu göndermek için buton
submit_button = st.button("Sorguyu Çalıştır")

if query and (submit_button or st.session_state.get('auto_submit', False)):
    with st.spinner('SQL sorgusu oluşturuluyor...'):
        sql = to_sql_query(query, schema)
    
    st.subheader("Oluşturulan SQL Sorgusu:")
    st.code(sql, language="sql")
    
    # SQL sorgusunu çalıştır ve sonuçları göster
    try:
        import pandas as pd
        from sqlalchemy import text
        engine = create_engine(db_url)
        with engine.connect() as conn:
            df = pd.read_sql_query(text(sql), conn)
            
        st.subheader("Sorgu Sonuçları:")
        st.dataframe(df)
        
        # Sonuçları indirme bağlantısı ekle
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="Sonuçları İndir (CSV)",
            data=csv,
            file_name='sorgu_sonuclari.csv',
            mime='text/csv',
        )
            
    except Exception as e:
        st.error(f"Sorgu çalıştırılırken hata oluştu: {str(e)}")



