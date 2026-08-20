import streamlit as st
import requests
import pandas as pd
from datetime import date, timedelta

# ==========================================
# 1. НАЛАШТУВАННЯ
# ==========================================
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
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

hide_streamlit_style = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stApp > header {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

if 'form_key' not in st.session_state:
    st.session_state.form_key = 0
fk = st.session_state.form_key

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

def parse_dur(val_str):
    if not val_str: return 0.0
    try:
        return float(str(val_str).replace(',', '.'))
    except ValueError:
        return 0.0

@st.cache_data(ttl=60, show_spinner=False)
def fetch_equipment():
    url = f"https://api.notion.com/v1/databases/{EQUIPMENT_DB_ID}/query"
    equip_dict = {}
    equip_no_inv_list = []
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
            
            if name:
                clean_inv = inv_num.strip() if inv_num else ""
                if clean_inv:
                    # Якщо номер є - додаємо для пошуку
                    equip_dict[clean_inv] = {"name": name, "id": page['id']}
                    equip_dict[clean_inv.lstrip('0')] = {"name": name, "id": page['id']}
                else:
                    # Якщо номера немає - додаємо у список для вибору
                    equip_no_inv_list.append({"name": name, "id": page['id']})
                
        has_more = data.get('has_more', False)
        next_cursor = data.get('next_cursor')
        
    return equip_dict, equip_no_inv_list

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
    last_month = (date.today() - timedelta(days=30)).isoformat()
    url = f"https://api.notion.com/v1/databases/{TICKETS_DB_ID}/query"
    
    tickets = []
    has_more = True
    next_cursor = None
    
    while has_more:
        payload = {
            "page_size": 100,
            "filter": {"property": "Дата", "date": {"on_or_after": last_month}},
            "sorts": [{"property": "Дата", "direction": "descending"}]
        }
        if next_cursor:
            payload["start_cursor"] = next_cursor
            
        response = requests.post(url, headers=HEADERS, json=payload)
        if response.status_code != 200: break
        
        data = response.json()
        for page in data.get('results', []):
            props = page['properties']
            
            date_data = props.get('Дата', {}).get('date')
            t_date = date_data.get('start', "") if date_data else ""
            
            desc = get_prop_text(props.get('Короткий опис'))
            
            mech_rel = props.get('Виконавець', {}).get('relation', [])
            mech_id = mech_rel[0]['id'] if mech_rel else None
            
            inv_rel = props.get('Інвентарний номер', {}).get('relation', [])
            inv_id = inv_rel[0]['id'] if inv_rel else None
            
            rep_data = props.get('Вид ремонту', {}).get('select')
            r_type = rep_data.get('name', "") if rep_data else ""
            
            # Додаємо зчитування ЗМІНИ
            shift_data = props.get('Зміна', {}).get('select')
            shift = shift_data.get('name', "Не вказано") if shift_data else "Не вказано"
            
            dur_data = props.get('Фактична тривалість', {}).get('number')
            duration = dur_data if dur_data is not None else 0
            
            tickets.append({
                "Дата": t_date, 
                "Опис": desc, 
                "Вид ремонту": r_type, 
                "Зміна": shift, # Зберігаємо зміну
                "Години": duration, 
                "mech_id": mech_id, 
                "inv_id": inv_id
            })
            
        has_more = data.get('has_more', False)
        next_cursor = data.get('next_cursor')
        
    return tickets

with st.spinner('⚙️ Синхронізація з базами Notion... Будь ласка, зачекайте...'):
    equip_data, equip_no_inv_list = fetch_equipment()
    staff_data = fetch_staff()
    managers_data = fetch_managers()

staff_names = list(staff_data.keys())
manager_names = list(managers_data.keys())

# ==========================================
# 3. ІНТЕРФЕЙС ТА ВКЛАДКИ
# ==========================================
st.title("🛠 Тікет на виконання ремонтних робіт")

tab1, tab2 = st.tabs(["📝 Створення тікета", "📊 Історія робіт (останні 30 днів)"])

# ----------------- ВКЛАДКА 1: ФОРМА -----------------
with tab1:
    if st.session_state.get('show_success', False):
        st.success("✅ Тікет успішно створено в Notion!")
        st.toast("Механізм запущено! Тікет у роботі ⚙️🔧", icon="⚙️")
        st.session_state.show_success = False

    default_idx = 0
    for i, name in enumerate(manager_names):
        if "Дубинецький" in name:
            default_idx = i
            break

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Загальна інформація")
        selected_date = st.date_input("Дата", value=date.today(), key=f"date_{fk}")
        
        no_inv = st.checkbox("⚙️ Обладнання без інвентарного номера", key=f"check_inv_{fk}")
        
        equip_name = "Поточні ремонтні роботи"
        equip_page_id = None
        
        if no_inv:
            # У списку будуть ТІЛЬКИ ті, в кого пусте поле інвентарного номера
            no_inv_names = sorted(list(set([e['name'] for e in equip_no_inv_list if e['name']])))
            selected_name = st.selectbox("Оберіть обладнання зі списку:", ["Оберіть..."] + no_inv_names, key=f"sel_eq_{fk}")
            
            if selected_name != "Оберіть...":
                equip_name = selected_name
                for e in equip_no_inv_list:
                    if e['name'] == selected_name:
                        equip_page_id = e['id']
                        break
                st.success(f"✅ Обрано: **{equip_name}**")
        else:
            inv_number = st.text_input("Інвентарний номер обладнання", placeholder="Введіть код...", key=f"inv_{fk}").strip()
            if inv_number:
                clean_inv = inv_number.lstrip('0')
                if clean_inv in equip_data:
                    equip_name = equip_data[clean_inv]["name"]
                    equip_page_id = equip_data[clean_inv]["id"]
                    st.success(f"✅ Обладнання: **{equip_name}**")
                else:
                    st.error("⚠️ Обладнання не знайдено. Буде записано як 'Поточні ремонтні роботи'")
            else:
                st.info("ℹ️ Номер не вказано. Буде записано як 'Поточні ремонтні роботи'")

        mechanic = st.selectbox("Виконавець ремонту", ["Оберіть..."] + staff_names, key=f"mech_{fk}")

    with col2:
        st.subheader("Деталі ремонту")
        repair_type = st.selectbox("Вид ремонту", ["Поточний", "Капітальний", "Модернізація", "Створення нового", "Експлуатація"], key=f"rep_{fk}")
        shift = st.selectbox("Зміна", ["денна", "нічна", "понаднормово", "екстрений виклик","відрядження"], key=f"shift_{fk}")
        
        col_dur1, col_dur2 = st.columns(2)
        with col_dur1:
            plan_dur_str = st.text_input("Планова тривалість (год)", placeholder="Наприклад: 1.5 або 1,5", key=f"plan_{fk}")
        with col_dur2:
            fact_dur_str = st.text_input("Фактична тривалість (год)", placeholder="Наприклад: 1.5 або 1,5", key=f"fact_{fk}")
        
        manager = st.selectbox("Прийняв роботу", manager_names, index=default_idx, key=f"man_{fk}")

    st.markdown("---")

    comment = st.text_area("Опис ремонту (що було зроблено)", placeholder="Введіть деталі проведених робіт...", key=f"com_{fk}")

    st.markdown("---")

    if st.button("Відправити тікет 🚀", use_container_width=True):
        if mechanic == "Оберіть...":
            st.warning("Будь ласка, оберіть виконавця!")
        else:
            plan_dur = parse_dur(plan_dur_str)
            fact_dur = parse_dur(fact_dur_str)
            
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
                    "Зміна": { "select": {"name": shift} },
                    "Планова тривалість": { "number": plan_dur },
                    "Фактична тривалість": { "number": fact_dur }
                }
            }
            
            post_url = "https://api.notion.com/v1/pages"
            res = requests.post(post_url, headers=HEADERS, json=new_page_data)
            
            if res.status_code == 200:
                fetch_recent_tickets.clear()
                st.session_state.show_success = True
                st.session_state.form_key += 1 
                st.rerun()
            else:
                st.error(f"Помилка відправки: {res.text}")

# ----------------- ВКЛАДКА 2: ІСТОРІЯ -----------------
with tab2:
    st.subheader("📊 База виконаних робіт за місяць")
    recent_tickets = fetch_recent_tickets()
    
    if recent_tickets:
        staff_id_to_name = {v: k for k, v in staff_data.items()}
        equip_id_to_name = {v["id"]: v["name"] for k, v in equip_data.items()}
        for e in equip_no_inv_list:
            equip_id_to_name[e["id"]] = e["name"]
        
        for t in recent_tickets:
            t["Виконавець"] = staff_id_to_name.get(t["mech_id"], "Не вказано")
            t["Обладнання"] = equip_id_to_name.get(t["inv_id"], "Поточні роботи / Не вказано")
            
        df = pd.DataFrame(recent_tickets)
        # Додаємо колонку "Зміна" у таблицю
        df = df[["Дата", "Виконавець", "Обладнання", "Опис", "Вид ремонту", "Зміна", "Години"]]
        
        filter_mechanic = st.selectbox("🔍 Фільтр по виконавцю:", ["Всі"] + sorted(staff_names))
        if filter_mechanic != "Всі":
            df = df[df["Виконавець"] == filter_mechanic]
            
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"Знайдено записів: {len(df)}")
            
            st.markdown("---")
            st.markdown("### ⏱ Підсумки годин (за вибраними записами)")
            
            # Рахуємо суму годин по кожній зміні
            summary_df = df.groupby('Зміна')['Години'].sum().reset_index()
            
            # Виводимо красиві блоки (метрики)
            col_metrics = st.columns(len(summary_df) + 1)
            
            for idx, row in summary_df.iterrows():
                with col_metrics[idx]:
                    st.metric(label=f"Зміна: {row['Зміна']}", value=f"{row['Години']} год")
                    
            with col_metrics[-1]:
                st.metric(label="🔥 Всього годин", value=f"{df['Години'].sum()} год")
                
        else:
            st.info(f"Для виконавця **{filter_mechanic}** за останній місяць записів не знайдено.")
    else:
        st.info("За останній місяць немає жодного запису в реєстрі.")
