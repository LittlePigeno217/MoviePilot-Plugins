import re
with open('Page.vue', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('props.api.get(\\plugin/\/status)', "props.api.get(\plugin/\/status\)")
content = content.replace('props.api.post(\\plugin/\/run)', "props.api.post(\plugin/\/run\)")
with open('Page.vue', 'w', encoding='utf-8') as f:
    f.write(content)
