import streamlit as st
import requests
import pandas as pd
from datetime import date, timedelta

# ==========================================
# 1. НАЛАШТУВАННЯ
# ==========================================
NOTION_TOKEN = "ntn_G57772874227mq1hCIkHyST2twvBfzGWKpnhnvCMzrmdMf"
EQUIPMENT_DB_ID = "3c01585a68fe8050b21cda745390d13c"
STAFF_DB_ID = "3c01585a68fe80608f94fe6bba5068a8"
MANAGERS_DB_ID = "3c01585a68fe8055900adee2bec8e6de"
TICKETS_DB_ID = "3c01585a68fe800ab693cd14f0768717"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

st.set_page_config(page_title="Тікет на ремонт", layout="wide")

# ПРИХОВУЄМО ТЕХНІЧНІ ЕЛЕМЕНТИ (CSS МАГІЯ)
hide_streamlit_style = """
<style>
    /* Ховаємо меню з трьома крапками (там і так немає нічого корисного для користувача) */
    #MainMenu {visibility: hidden;}
    
    /* Ховаємо напис "Made with Streamlit" внизу */
    footer {visibility: hidden;}
    
    /* Ховаємо написи "Running..." в правому верхньому куті */
    .stApp > header {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ==========================================
# 2. ДОПОМІЖНІ ФУНКЦІЇ
# ==========================================
def get_prop_text(prop):
    if not prop: return ""
    prop_type = prop.get('type')
    if prop_type == 'title':
        return "".join([t['plain_text'] for t in prop.get('title', [])])
    elif prop_type == 'rich_text':
        return "".join([t['plain_text'] for t in prop.get('rich_text', [])])
    elif prop_type == 'number':
        num = prop.get('number')
        if num is None: return ""
        if isinstance(num, float) and num.is_integer():
            return str(int(num))
        return str(num)
    return ""

@st.cache_data(ttl=60, show_spinner=False)
def fetch_equipment():
    url = f"https://api.notion.com/v1/databases/{EQUIPMENT_DB_ID}/query"
    equip_dict = {}
    has_more = True
    next_cursor = None
    
    while has_more:
        payload = {"page_size": 100}
        if next_cursor: payload["start_cursor"] = next_cursor
            
        response = requests.post(url, headers=HEADERS, json=payload)
        if response.status_code != 200: break
            
        data = response.json()
        for page in data.get('results', []):
            props = page['properties']
            inv_num = get_prop_text(props.get('Інвентарний номер') or props.get('Код'))
            name = get_prop_text(props.get('Полное наименование') or props.get('Назва обладнання') or props.get('Наименование'))
            if inv_num:
                equip_dict[inv_num.strip()] = {"name": name, "id": page['id']}
                
        has_more = data.get('has_more', False)
        next_cursor = data.get('next_cursor')
        
    return equip_dict

@st.cache_data(ttl=60, show_spinner=False)
def fetch_staff():
    url = f"https://api.notion.com/v1/databases/{STAFF_DB_ID}/query"
    response = requests.post(url, headers=HEADERS)
    staff_dict = {}
    if response.status_code == 200:
        for page in response.json().get('results', []):
            name = get_prop_text(page['properties'].get('Name') or page['properties'].get('Співробітник')) 
            if name: staff_dict[name.strip()] = page['id']
    return staff_dict

@st.cache_data(ttl=60, show_spinner=False)
def fetch_managers():
    url = f"https://api.notion.com/v1/databases/{MANAGERS_DB_ID}/query"
    response = requests.post(url, headers=HEADERS)
    managers_dict = {}
    if response.status_code == 200:
        for page in response.json().get('results', []):
            name = get_prop_text(page['properties'].get('Name') or page['properties'].get('Співробітник'))
            if name: managers_dict[name.strip()] = page['id']
    return managers_dict

@st.cache_data(ttl=60, show_spinner=False)
def fetch_recent_tickets():
    """Витягує тікети за останні 30 днів"""
    last_month = (date.today() - timedelta(days=30)).isoformat()
    url = f"https://api.notion.com/v1/databases/{TICKETS_DB_ID}/query"
    
    # Фільтруємо тікети напряму в Notion (тільки новіші за 30 днів тому)
    payload = {
        "filter": {
            "property": "Дата",
            "date": {"on_or_after": last_month}
        },
        "sorts": [{"property": "Дата", "direction": "descending"}]
    }
    
    response = requests.post(url, headers=HEADERS, json=payload)
    tickets = []
    
    if response.status_code == 200:
        data = response.json()
        for page in data.get('results', []):
            props = page['properties']
            
            date_prop = props.get('Дата', {}).get('date')
            t_date = date_prop.get('start') if date_prop else ""
            
            desc = get_prop_text(props.get('Короткий опис'))
            
            # Витягуємо ID Виконавця
            mech_rel = props.get('Виконавець', {}).get('relation', [])
            mech_id = mech_rel[0]['id'] if mech_rel else None
            
            # Витягуємо ID Обладнання (Інвентарний номер)
            inv_rel = props.get('Інвентарний номер', {}).get('relation', [])
            inv_id = inv_rel[0]['id'] if inv_rel else None
            
            repair_type = props.get('Вид ремонту', {}).get('select', {})
            r_type = repair_type.get('name') if repair_type else ""
            
            duration = props.get('Фактична тривалість', {}).get('number', 0)
            if duration is None: duration = 0

            tickets.append({
                "Дата": t_date,
                "Опис": desc,
                "Вид ремонту": r_type,
                "Години": duration,
                "mech_id": mech_id,
                "inv_id": inv_id
            })
    return tickets

with st.spinner('⚙️ Синхронізація з базами Notion... Будь ласка, зачекайте...'):
    equip_data = fetch_equipment()
    staff_data = fetch_staff()
    managers_data = fetch_managers()

staff_names = list(staff_data.keys())
manager_names = list(managers_data.keys())

# ==========================================
# 3. ІНТЕРФЕЙС ТА ВКЛАДКИ
# ==========================================
st.title("🛠 Тікет на виконання ремонтних робіт")

# СТВОРЮЄМО ДВІ ВКЛАДКИ
tab1, tab2 = st.tabs(["📝 Створення тікета", "📊 Історія робіт (останні 30 днів)"])

# ----------------- ВКЛАДКА 1: ФОРМА -----------------
with tab1:
    default_idx = 0
    for i, name in enumerate(manager_names):
        if "Дубинецький" in name:
            default_idx = i
            break

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Загальна інформація")
        selected_date = st.date_input("Дата", value=date.today())
        
        inv_number = st.text_input("Інвентарний номер обладнання", placeholder="Введіть код або залиште пустим...").strip()
        
        equip_name = "Поточні ремонтні роботи"
        equip_page_id = None
        
        if inv_number:
            if inv_number in equip_data:
                equip_name = equip_data[inv_number]["name"]
                equip_page_id = equip_data[inv_number]["id"]
                st.success(f"✅ Обладнання: **{equip_name}**")
            else:
                st.error("⚠️ Обладнання не знайдено. Буде записано як 'Поточні ремонтні роботи'")
        else:
            st.info("ℹ️ Номер не вказано. Буде записано як 'Поточні ремонтні роботи'")

        mechanic = st.selectbox("Виконавець ремонту", ["Оберіть..."] + staff_names)

    with col2:
        st.subheader("Деталі ремонту")
        repair_type = st.selectbox("Вид ремонту", ["Поточний", "Капітальний", "Модернізація", "Створення нового", "Експлуатація"])
        shift = st.selectbox("Зміна", ["денна", "нічна", "понаднормово", "екстрений виклик","відрядження"])
        
        col_dur1, col_dur2 = st.columns(2)
        with col_dur1:
            plan_dur = st.number_input("Планова тривалість (год)", min_value=0.0, step=0.5)
        with col_dur2:
            fact_dur = st.number_input("Фактична тривалість (год)", min_value=0.0, step=0.5)
        
        manager = st.selectbox("Прийняв роботу", manager_names, index=default_idx)

    st.markdown("---")

    comment = st.text_area("Опис ремонту (що було зроблено)", placeholder="Введіть деталі проведених робіт...")

    st.markdown("---")

    if st.button("Відправити тікет 🚀", use_container_width=True):
        if mechanic == "Оберіть...":
            st.warning("Будь ласка, оберіть виконавця!")
        else:
            equip_relation = [{"id": equip_page_id}] if equip_page_id else []
            ticket_title = comment.strip() if comment.strip() else "Без опису"

            new_page_data = {
                "parent": {"database_id": TICKETS_DB_ID},
                "properties": {
                    "Короткий опис": { "title": [{"text": {"content": ticket_title}}] },
                    "Дата": { "date": {"start": str(selected_date)} },
                    "Інвентарний номер": { "relation": equip_relation },
                    "Виконавець": { "relation": [{"id": staff_data[mechanic]}] },
                    "Прийняв роботу": { "relation": [{"id": managers_data[manager]}] },
                    "Вид ремонту": { "select": {"name": repair_type} },
                    "Планова тривалість": { "number": plan_dur },
                    "Фактична тривалість": { "number": fact_dur }
                }
            }
            
            post_url = "https://api.notion.com/v1/pages"
            res = requests.post(post_url, headers=HEADERS, json=new_page_data)
            
            if res.status_code == 200:
                st.success("✅ Тікет успішно створено в Notion!")
                st.toast("Механізм запущено! Тікет у роботі ⚙️🔧", icon="⚙️")
                # Очищаємо кеш тікетів, щоб таблиця відразу оновилась
                fetch_recent_tickets.clear()
            else:
                st.error(f"Помилка відправки: {res.text}")

# ----------------- ВКЛАДКА 2: ІСТОРІЯ -----------------
with tab2:
    st.subheader("📊 База виконаних робіт за місяць")
    
    # Завантажуємо тікети
    recent_tickets = fetch_recent_tickets()
    
    if recent_tickets:
        # Створюємо словники для перекладу ID назад у зрозумілі назви
        staff_id_to_name = {v: k for k, v in staff_data.items()}
        equip_id_to_name = {v["id"]: v["name"] for k, v in equip_data.items()}
        
        # Перекладаємо ID у нормальні тексти
        for t in recent_tickets:
            t["Виконавець"] = staff_id_to_name.get(t["mech_id"], "Не вказано")
            t["Обладнання"] = equip_id_to_name.get(t["inv_id"], "Поточні роботи / Не вказано")
            
        # Створюємо DataFrame з Pandas для красивої таблиці
        df = pd.DataFrame(recent_tickets)
        
        # Переставляємо колонки місцями для краси
        df = df[["Дата", "Виконавець", "Обладнання", "Опис", "Вид ремонту", "Години"]]
        
        # Відмальовуємо фільтр
        filter_mechanic = st.selectbox("🔍 Фільтр по виконавцю:", ["Всі"] + sorted(staff_names))
        
        # Застосовуємо фільтр, якщо обрано когось конкретного
        if filter_mechanic != "Всі":
            df = df[df["Виконавець"] == filter_mechanic]
            
        if not df.empty:
            # Виводимо таблицю. use_container_width розтягує її на весь екран
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"Знайдено записів: {len(df)}")
        else:
            st.info(f"Для виконавця **{filter_mechanic}** за останній місяць записів не знайдено.")
    else:
        st.info("За останній місяць немає жодного запису в реєстрі.")