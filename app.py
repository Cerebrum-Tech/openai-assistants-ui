import os
from dotenv import load_dotenv
import time
import glob
import base64
import re
import streamlit as st
import openai
from openai.types.beta.threads import MessageContentImageFile

load_dotenv()


# OpenAI API
api_key = os.environ.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)
assistant_id = os.environ.get("ASSISTANT_ID")
instructions = os.environ.get(
    "RUN_INSTRUCTIONS") or None
bot_title = os.environ.get("BOT_TITLE") or "Cere Code Interpreter"
settings_on = os.environ.get("SETTINGS_ON") or False
file_ids = [os.environ.get("FILE_ID")]


def create_thread(content, file):
    messages = [
        {
            "role": "user",
            "content": content,
        }
    ]
    if file is not None:
        messages[0].update({"file_ids": [file.id]})
    thread = client.beta.threads.create(messages=messages)
    return thread


def create_message(thread, content, file):
    file_ids = []
    client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=content, file_ids=file_ids
    )
    if file is not None:
        file_ids.append(file.id)


def create_run(thread):
    run = client.beta.threads.runs.create(
        thread_id=thread.id, assistant_id=assistant_id, instructions=instructions
    )
    return run


def create_file_link(file_name, file_id):
    content = client.files.content(file_id)
    content_type = content.response.headers["content-type"]
    b64 = base64.b64encode(content.text.encode(content.encoding)).decode()
    link_tag = f'<a href="data:{content_type};base64,{b64}" download="{file_name}">Download Link</a>'
    return link_tag


def get_message_value_list(messages):
    messages_value_list = []
    for message in messages:
        message_content = ""
        print("message", message)
        if not isinstance(message, MessageContentImageFile) and hasattr(message.content[0], "text"):
            print("message.content:", message.content)
            message_content = message.content[0].text
            annotations = message_content.annotations
        else:
            print("message.file_id:", message.content[0].image_file.file_id)
            image_data = client.files.content(
                message.content[0].image_file.file_id)
            image_data_bytes = image_data.read()
            image_data_base64 = base64.b64encode(image_data_bytes).decode()
            image_tag = f'<img src="data:image/png;base64,{image_data_base64}" width="400">'
            message_content = st.markdown(image_tag, True)
            messages_value_list.append(
                f"{image_tag}\n\n"
            )
            annotations = []
            continue
        citations = []
        for index, annotation in enumerate(annotations):
            message_content.value = message_content.value.replace(
                annotation.text, f" [{index}]"
            )

            if file_citation := getattr(annotation, "file_citation", None):
                cited_file = client.files.retrieve(file_citation.file_id)
                citations.append(
                    f"[{index}] {file_citation.quote} from {cited_file.filename}"
                )
            elif file_path := getattr(annotation, "file_path", None):
                link_tag = create_file_link(
                    annotation.text.split("/")[-1], file_path.file_id
                )
                message_content.value = re.sub(
                    r"\[(.*?)\]\s*\(\s*(.*?)\s*\)", link_tag, message_content.value
                )

        message_content.value += "\n" + "\n".join(citations)
        messages_value_list.append(message_content.value)
        return messages_value_list


def get_message_list(thread, run):
    completed = False
    while not completed:
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id, run_id=run.id)
        print("run.status:", run.status)
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        print("messages:", "\n".join(get_message_value_list(messages)))
        if run.status == "completed":
            completed = True
        else:
            time.sleep(5)

    messages = client.beta.threads.messages.list(thread_id=thread.id)
    return get_message_value_list(messages)


def get_response(user_input, file):
    if "thread" not in st.session_state:
        st.session_state.thread = create_thread(user_input, file)
    else:
        create_message(st.session_state.thread, user_input, file)
    run = create_run(st.session_state.thread)
    return "\n".join(get_message_list(st.session_state.thread, run))


def handle_uploaded_file(uploaded_file):
    file = client.files.create(file=uploaded_file, purpose="assistants")
    return file


def render_chat():
    for chat in st.session_state.chat_log:
        with st.chat_message(chat["name"]):
            st.markdown(chat["msg"], True)


if "chat_log" not in st.session_state:
    st.session_state.chat_log = []

if "in_progress" not in st.session_state:
    st.session_state.in_progress = False


def disable_form():
    st.session_state.in_progress = True


def main():

    st.set_page_config(
        page_title="Cere Code Interpreter",
        page_icon=":robot_face:",
    )
    st.title(bot_title)

    if settings_on:

        instructions = st.sidebar.text_area("Enter your instructions", height=200,
                                            value="You are a helpful assistant that answers questions based on uploaded files.")
        uploaded_file = st.sidebar.file_uploader(
            "Upload a file",
            type=[
                "txt",
                "pdf",
                "png",
                "jpg",
                "jpeg",
                "csv",
                "json",
                "geojson",
                "xlsx",
                "xls",
            ],
            disabled=st.session_state.in_progress,
        )
    else:
        uploaded_file = None
    user_msg = st.chat_input(
        "Message", on_submit=disable_form, disabled=st.session_state.in_progress
    )

    if user_msg:
        render_chat()
        with st.chat_message("user"):
            st.markdown(user_msg, True)
        file = None
        if uploaded_file is not None:
            file = handle_uploaded_file(uploaded_file)
        response = get_response(user_msg, file)
        with st.chat_message("Assistant"):
            st.markdown(response, True)

        st.session_state.chat_log.append({"name": "user", "msg": user_msg})
        st.session_state.chat_log.append(
            {"name": "assistant", "msg": response})
        st.session_state.in_progress = False
        st.rerun()
    render_chat()


if __name__ == "__main__":
    main()
