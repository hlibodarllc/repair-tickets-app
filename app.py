import streamlit as st
import requests
import pandas as pd
from datetime import date, timedelta
import time

# ==========================================
# 1. НАЛАШТУВАННЯ
# ==========================================
NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
EQUIPMENT_DB_ID = "3c01585a68fe8050b21cda745390d13c"
STAFF_DB_ID = "3c01585a68fe80608f94fe6bba5068a8"
MANAGERS_DB_ID = "3c01585a68fe8055900adee2bec8e6de"
TICKETS_DB_ID = "3c01585a68fe800ab693cd14f0768717"
TIME_TRACKING_DB_ID = "3c91585a68fe80f4a5bee29bffa23d2a"

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
if 'time_form_key' not in st.session_state:
    st.session_state.time_form_key = 0
    
fk = st.session_state.form_key
fk_time = st.session_state.time_form_key

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
                    equip_dict[clean_inv] = {"name": name, "id": page['id']}
                    equip_dict[clean_inv.lstrip('0')] = {"name": name, "id": page['id']}
                else:
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
def fetch_recent_tickets(start_date_str, end_date_str):
    url = f"https://api.notion.com/v1/databases/{TICKETS_DB_ID}/query"
    tickets = []
    has_more = True
    next_cursor = None
    
    while has_more:
        payload = {
            "page_size": 100,
            "filter": {
                "and": [
                    {"property": "Дата", "date": {"on_or_after": start_date_str}},
                    {"property": "Дата", "date": {"on_or_before": end_date_str}}
                ]
            },
            "sorts": [{"property": "Дата", "direction": "descending"}]
        }
        if next_cursor: payload["start_cursor"] = next_cursor
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
            shift_data = props.get('Зміна', {}).get('select')
            shift = shift_data.get('name', "Не вказано") if shift_data else "Не вказано"
            dur_data = props.get('Фактична тривалість', {}).get('number')
            duration = dur_data if dur_data is not None else 0
            
            tickets.append({
                "Дата": t_date, 
                "Опис": desc, 
                "Вид ремонту": r_type, 
                "Зміна": shift,
                "Години": duration, 
                "mech_id": mech_id, 
                "inv_id": inv_id
            })
            
        has_more = data.get('has_more', False)
        next_cursor = data.get('next_cursor')
        
    return tickets

# --- НОВА ФУНКЦІЯ ДЛЯ ЖУРНАЛУ ВІДСУТНОСТІ ---
@st.cache_data(ttl=60, show_spinner=False)
def fetch_recent_absences(start_date_str, end_date_str):
    url = f"https://api.notion.com/v1/databases/{TIME_TRACKING_DB_ID}/query"
    absences = []
    has_more = True
    next_cursor = None
    
    while has_more:
        payload = {
            "page_size": 100,
            "filter": {
                "and": [
                    {"property": "Дата", "date": {"on_or_after": start_date_str}},
                    {"property": "Дата", "date": {"on_or_before": end_date_str}}
                ]
            },
            "sorts": [{"property": "Дата", "direction": "descending"}]
        }
        if next_cursor: payload["start_cursor"] = next_cursor
        response = requests.post(url, headers=HEADERS, json=payload)
        if response.status_code != 200: break
        
        data = response.json()
        for page in data.get('results', []):
            props = page['properties']
            
            date_data = props.get('Дата', {}).get('date')
            t_date = date_data.get('start', "") if date_data else ""
            
            mech_rel = props.get('Виконавець', {}).get('relation', [])
            mech_id = mech_rel[0]['id'] if mech_rel else None
            
            act_data = props.get('Вид діяльності', {}).get('select')
            activity = act_data.get('name', "") if act_data else ""
            
            dur_data = props.get('Фактична тривалість', {}).get('number')
            duration = dur_data if dur_data is not None else 0
            
            desc = get_prop_text(props.get('Опис'))
            
            man_rel = props.get('Погодив', {}).get('relation', [])
            man_id = man_rel[0]['id'] if man_rel else None

            absences.append({
                "Дата": t_date,
                "Виконавець_id": mech_id,
                "Вид діяльності": activity,
                "Години": duration,
                "Опис": desc,
                "Погодив_id": man_id
            })
            
        has_more = data.get('has_more', False)
        next_cursor = data.get('next_cursor')
        
    return absences

with st.spinner('⚙️ Синхронізація з базами Notion... Будь ласка, зачекайте...'):
    equip_data, equip_no_inv_list = fetch_equipment()
    staff_data = fetch_staff()
    managers_data = fetch_managers()

staff_names = list(staff_data.keys())
manager_names = list(managers_data.keys())

# ==========================================
# 3. ІНТЕРФЕЙС ТА ВКЛАДКИ
# ==========================================
st.title("🛠 Внутрішній портал механіків")

# Перегрупували вкладки: спочатку форми, потім журнали
tab_create_ticket, tab_create_time, tab_history_ticket, tab_history_time = st.tabs([
    "📝 Створення тікета", 
    "⏱ Облік часу", 
    "📊 Історія робіт", 
    "📅 Журнал відсутності"
])

is_any_sent = st.session_state.get('ticket_sent', False) or st.session_state.get('time_sent', False)
btn_color = "#28a745" if is_any_sent else "#ED7117"

st.markdown(f"""
<style>
button[kind="primary"] {{
    background-color: {btn_color} !important;
    border-color: {btn_color} !important;
    color: white !important;
    transition: background-color 0.4s ease;
}}
button[kind="primary"]:hover {{
    filter: brightness(1.1);
}}
</style>
""", unsafe_allow_html=True)


# ----------------- ВКЛАДКА 1: СТВОРЕННЯ ТІКЕТА -----------------
with tab_create_ticket:
    btn_text1 = "✅ Тікет успішно відправлено!" if st.session_state.get('ticket_sent') else "Відправити тікет 🚀"

    if st.session_state.get('show_success', False):
        st.toast("Механізм запущено! Тікет у роботі ⚙️", icon="✅")
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
        
        # Прибрали планову тривалість
        fact_dur_str = st.text_input("Фактична тривалість (год)", placeholder="Наприклад: 1.5", key=f"fact_{fk}")
        
        fact_dur_val = parse_dur(fact_dur_str)
        confirm_long = False
        if fact_dur_val > 12:
            st.warning("⏱ Вказано більше 12 годин! Це не помилка?")
            confirm_long = st.checkbox("Підтверджую, відпрацьовано > 12 год.", key=f"conf_12_{fk}")
        
        manager = st.selectbox("Прийняв роботу", manager_names, index=default_idx, key=f"man_{fk}")

    st.markdown("---")
    comment = st.text_area("Опис ремонту (що було зроблено)", placeholder="Введіть деталі проведених робіт...", key=f"com_{fk}")
    st.markdown("---")

    if st.button(btn_text1, type="primary", use_container_width=True, key=f"btn_ticket_{fk}"):
        if mechanic == "Оберіть...":
            st.warning("Будь ласка, оберіть виконавця!")
        elif fact_dur_val > 12 and not confirm_long:
            st.error("⚠️ Ви вказали понад 12 годин фактичної роботи. Підтвердіть галочкою, якщо це не помилка.")
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
                    "Зміна": { "select": {"name": shift} },
                    "Фактична тривалість": { "number": fact_dur_val }
                }
            }
            
            res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=new_page_data)
            if res.status_code == 200:
                fetch_recent_tickets.clear()
                st.session_state.ticket_sent = True
                st.session_state.show_success = True
                st.rerun()
            else:
                st.error(f"Помилка відправки: {res.text}")

    if st.session_state.get('ticket_sent', False):
        time.sleep(2)
        st.session_state.ticket_sent = False
        st.session_state.form_key += 1
        st.rerun()

# ----------------- ВКЛАДКА 2: ОБЛІК ЧАСУ -----------------
with tab_create_time:
    btn_text3 = "✅ Запис успішно збережено!" if st.session_state.get('time_sent') else "Записати години 🚀"

    if st.session_state.get('show_time_success', False):
        st.toast("Години успішно зафіксовано ⏱", icon="✅")
        st.session_state.show_time_success = False

    col3_1, col3_2 = st.columns(2)

    with col3_1:
        st.subheader("Основна інформація")
        selected_date_time = st.date_input("Дата", value=date.today(), key=f"t_date_{fk_time}")
        mechanic_time = st.selectbox("Виконавець", ["Оберіть..."] + staff_names, key=f"t_mech_{fk_time}")
        activity_type = st.selectbox("Вид діяльності", ["Відрядження", "Медогляд", "Відгул", "Відпустка", "Хвороба", "Інше"], key=f"t_act_{fk_time}")

    with col3_2:
        st.subheader("Тривалість та узгодження")
        
        # Прибрали планову тривалість
        fact_dur_t_str = st.text_input("Фактична тривалість (год)", placeholder="Наприклад: 8", key=f"t_fact_{fk_time}")
        
        fact_dur_t_val = parse_dur(fact_dur_t_str)
        confirm_long_t = False
        if fact_dur_t_val > 12:
            st.warning("⏱ Більше 12 годин!")
            confirm_long_t = st.checkbox("Підтверджую > 12 год.", key=f"t_conf_{fk_time}")
            
        manager_time = st.selectbox("Погодив", manager_names, index=default_idx, key=f"t_man_{fk_time}")

    st.markdown("---")
    comment_time = st.text_area("Опис (деталі)", placeholder="Уточніть інформацію (наприклад, куди відрядження або причина відгулу)...", key=f"t_com_{fk_time}")
    st.markdown("---")

    if st.button(btn_text3, type="primary", use_container_width=True, key=f"btn_time_{fk_time}"):
        if mechanic_time == "Оберіть...":
            st.warning("Будь ласка, оберіть виконавця!")
        elif fact_dur_t_val > 12 and not confirm_long_t:
            st.error("⚠️ Ви вказали понад 12 годин. Підтвердіть галочкою, якщо це не помилка.")
        else:
            title_text = f"{activity_type} - {mechanic_time}"
            desc_text = comment_time.strip() if comment_time.strip() else ""

            time_page_data = {
                "parent": {"database_id": TIME_TRACKING_DB_ID},
                "properties": {
                    "Назва": { "title": [{"text": {"content": title_text}}] },
                    "Дата": { "date": {"start": str(selected_date_time)} },
                    "Виконавець": { "relation": [{"id": staff_data[mechanic_time]}] },
                    "Вид діяльності": { "select": {"name": activity_type} },
                    "Фактична тривалість": { "number": fact_dur_t_val },
                    "Погодив": { "relation": [{"id": managers_data[manager_time]}] },
                    "Опис": { "rich_text": [{"text": {"content": desc_text}}] }
                }
            }
            
            res_t = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=time_page_data)
            if res_t.status_code == 200:
                fetch_recent_absences.clear() # Очищаємо кеш журналу відсутності
                st.session_state.time_sent = True
                st.session_state.show_time_success = True
                st.rerun()
            else:
                st.error(f"Помилка відправки: {res_t.text}")

    if st.session_state.get('time_sent', False):
        time.sleep(2)
        st.session_state.time_sent = False
        st.session_state.time_form_key += 1
        st.rerun()


# ----------------- ВКЛАДКА 3: ІСТОРІЯ РЕМОНТІВ -----------------
with tab_history_ticket:
    st.subheader("📊 База виконаних ремонтних робіт")
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        default_start = date.today() - timedelta(days=30)
        default_end = date.today()
        selected_dates = st.date_input("🗓 Оберіть період:", value=(default_start, default_end), key="date_range_tickets")
    with col_f2:
        filter_mechanic = st.selectbox("🔍 Фільтр по виконавцю:", ["Всі"] + sorted(staff_names), key="filter_mech_tickets")
        
    if len(selected_dates) == 2:
        start_d, end_d = selected_dates
    else:
        start_d = selected_dates[0]
        end_d = selected_dates[0]
        
    start_str = start_d.isoformat()
    end_str = end_d.isoformat()
    
    recent_tickets = fetch_recent_tickets(start_str, end_str)
    
    if recent_tickets:
        staff_id_to_name = {v: k for k, v in staff_data.items()}
        equip_id_to_name = {v["id"]: v["name"] for k, v in equip_data.items()}
        for e in equip_no_inv_list:
            equip_id_to_name[e["id"]] = e["name"]
        
        for t in recent_tickets:
            t["Виконавець"] = staff_id_to_name.get(t["mech_id"], "Не вказано")
            t["Обладнання"] = equip_id_to_name.get(t["inv_id"], "Поточні роботи / Не вказано")
            
        df = pd.DataFrame(recent_tickets)
        df = df[["Дата", "Виконавець", "Обладнання", "Опис", "Вид ремонту", "Зміна", "Години"]]
        
        if filter_mechanic != "Всі":
            df = df[df["Виконавець"] == filter_mechanic]
            
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"Знайдено записів: {len(df)}")
            
            st.markdown("---")
            st.markdown(f"### ⏱ Підсумки годин (за обраний період)")
            
            summary_df = df.groupby('Зміна')['Години'].sum().reset_index()
            col_metrics = st.columns(len(summary_df) + 1)
            
            for idx, row in summary_df.iterrows():
                with col_metrics[idx]:
                    st.metric(label=f"Зміна: {row['Зміна']}", value=f"{row['Години']} год")
                    
            with col_metrics[-1]:
                st.metric(label="🔥 Всього годин", value=f"{df['Години'].sum()} год")
        else:
            st.info(f"Для виконавця **{filter_mechanic}** за обраний період записів не знайдено.")
    else:
        st.info("За обраний період немає жодного запису в реєстрі.")

# ----------------- ВКЛАДКА 4: ЖУРНАЛ ВІДСУТНОСТІ -----------------
with tab_history_time:
    st.subheader("📅 Журнал відсутності та іншої діяльності")
    
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        default_start_a = date.today() - timedelta(days=30)
        default_end_a = date.today()
        selected_dates_a = st.date_input("🗓 Оберіть період:", value=(default_start_a, default_end_a), key="date_range_abs")
    with col_a2:
        filter_mechanic_a = st.selectbox("🔍 Фільтр по виконавцю:", ["Всі"] + sorted(staff_names), key="filter_mech_abs")
        
    if len(selected_dates_a) == 2:
        start_d_a, end_d_a = selected_dates_a
    else:
        start_d_a = selected_dates_a[0]
        end_d_a = selected_dates_a[0]
        
    start_str_a = start_d_a.isoformat()
    end_str_a = end_d_a.isoformat()
    
    recent_absences = fetch_recent_absences(start_str_a, end_str_a)
    
    if recent_absences:
        staff_id_to_name = {v: k for k, v in staff_data.items()}
        man_id_to_name = {v: k for k, v in managers_data.items()}
        
        for a in recent_absences:
            a["Виконавець"] = staff_id_to_name.get(a["Виконавець_id"], "Не вказано")
            a["Погодив"] = man_id_to_name.get(a["Погодив_id"], "Не вказано")
            
        df_a = pd.DataFrame(recent_absences)
        df_a = df_a[["Дата", "Виконавець", "Вид діяльності", "Опис", "Години", "Погодив"]]
        
        if filter_mechanic_a != "Всі":
            df_a = df_a[df_a["Виконавець"] == filter_mechanic_a]
            
        if not df_a.empty:
            st.dataframe(df_a, use_container_width=True, hide_index=True)
            st.caption(f"Знайдено записів: {len(df_a)}")
            
            st.markdown("---")
            st.markdown(f"### ⏱ Підсумки годин (за обраний період)")
            
            # Групуємо години по виду діяльності (Відпустка, Хвороба тощо)
            summary_df_a = df_a.groupby('Вид діяльності')['Години'].sum().reset_index()
            col_metrics_a = st.columns(len(summary_df_a) + 1)
            
            for idx, row in summary_df_a.iterrows():
                with col_metrics_a[idx]:
                    st.metric(label=f"{row['Вид діяльності']}", value=f"{row['Години']} год")
                    
            with col_metrics_a[-1]:
                st.metric(label="🔥 Всього годин", value=f"{df_a['Години'].sum()} год")
        else:
            st.info(f"Для виконавця **{filter_mechanic_a}** за обраний період записів не знайдено.")
    else:
        st.info("За обраний період немає жодного запису в журналі.")
