# SYSTEM PROMPTING

### 1ST ROUND OF PROMPTING: system creation and developing

ok, i create a telegram channel. The telegram channel have the next structure:

- 1 owner: define the permissions
- 2 admins: the owner and 1 telegram bot
- 2 users: different than owners

i want implement the next functionalities:

- when the owner will send a message to group, per default, the bot need take this message and broadcast to every user as notification
- when user make a question to bot, the bot need to analyze the information in the internal group and reply to the user taking in account the user question and the last week message publications of the group as context to take in order to reply individually to the user. If the bot not found good answer or if the bot reply, but the user explicity answer that it's not satisfied, the bot pass the message to the owner answer the question. The main idea is filter the messages, the bot answer the mostly of the questions for the users, but when it's not enough, thus, the bot pass to the owner just the questions which he cannot reply correctly.

Let's take as reference the next code which manage a system of queue with llm:

assistant.py

and

rag/llm_client.py

and now you will need to add to me in another separate python script to manage some actions which the bot need to take inside of the system:

- the telegram bot need to collect the last 24 h of messages (text format) from the channel of telegram as context and add as context to the rag
- now in the llm_client.py, the script need to manage the question (or user message), the prompt and the context (collection of the last 24 h of messages in the telegram group) as the pieces to generate the answer
- the user of the telegram channel interact directly with the telegram bot. The user make a question. The system take the question, unify with the prompt, collect the messages from the last 24 h, add to the context and with the question + prompt + context, and finally produce the answer and return the answer to the channel in markdown format.
- after send the message, the user receive the reply, but need also show, the message together with 2 buttons options (YES and NO).
- if the telegram user press the button YES, it means the consultant is finished and the user is satisfied with the reply
- if the telegram user press the button NO, it means the consultant didn't have the desired answer. Thus press the button NO, implies that the bot inmediately will send the exaclty query from user and the information about the @username to the owner of the group to he can contact directly to the user about the question
- the interaction between owner, the bot, and the telegram users is like that:

1) the telegram channel publications is managed by the owner. He will redact the messages in the channel
2) when owner publish some message in the channel, after 1 h, the bot will reply the same message to each user (like some type of broadcast) say the message like: @user you have new important message! Message: `<the last message from the telegram channel>`
3) the users cannot send messages through the channel. They just can write to the telegram bot. The bot receive the message and manage as the steps mentioned before to can generate the correclty answer.
4) the telegram bot have priviledges as admin of the channel
5) just 1 telegram account called @master have permission as owner
6) the broadcast messages from telegram bot is just for members, not for the owner
7) per default, the bot will attent any question for any user. If user press button YES, it means, consultation finish. If it is the button NO, it means that need pass the same query and the username for the consultant to the owner of the group

integrate a new module in my python program in order to can i implement this functionality. Indeed, make the necessary changes and also take in account that is necessary manage the situation of many of users can make questions at the same time, and then, this system need to be managed as queue, taking as reference the script assistant_queue.py

Provide to me the step by step in order to can realize this functionality

### 2ND ROUND OF SYSTEM PROMPTING: tuning the functionality

Now is necessary make some correction. In the interaction flow between the user (not owner and not bot) and the bot, i remember tat we have the next flux of interaction to generate the replies:

User: "What was announced yesterday?"
  ?
Bot: [Processes with channel context]
  ?
Bot: "Based on the channel announcement, the meeting was..."
  ?
[Shows YES/NO buttons]
  ?
User clicks YES ? ? Marked as resolved
User clicks NO  ? ?? Escalated to owner

It is supossed that the bot will process the answer according to the channel context. Is supossed that the context collection is obtained in the next logic:

Channel ? Fetch Messages (24h) ? Cache ? LLM Context
                                    ?
                            TTL: 5 minutes

So, now i submit into test the system. The owner send the next 2 messages to the telegram channel (information related with the current price of the gold):

---- channel messages ------

[3/3/2026 11:59 AM] UPN CHANNEL: El precio del oro experimenta fluctuaciones este 3 de marzo de 2026, manteni?ndose por encima de los 5.300 d?lares por onza en el mercado internacional. Tras un repunte reciente impulsado por tensiones geopol?ticas en Oriente Medio (incluyendo acciones de EE.UU. e Israel contra Ir?n), el oro spot cotiza alrededor de 5.310-5.330 USD/onza, con ligeras correcciones por un d?lar m?s fuerte y mayores rendimientos de bonos.
[3/3/2026 3:48 PM] UPN CHANNEL: El metal precioso super? los US$ 5.400 por onza ante la intensificaci?n del conflicto entre Ir?n, Estados Unidos e Israel. La volatilidad geopol?tica y el riesgo sobre las rutas de suministro impulsan la demanda por activos refugio.
El precio del oro alcanz? este lunes su nivel m?s alto en un mes, extendiendo el rally iniciado la semana pasada en medio de la escalada del conflicto en Medio Oriente. El metal lleg? a subir hasta 2,9%, superando los US$ 5.400 por onza, antes de moderar parte de sus ganancias con la apertura de los mercados en Estados Unidos.

And then, the users make the next interactions with the bot (questions):

#### TEST 01:

Holger:
Porque motivo el precio de la onza de oro est? subiendo?

UPN Assistant:
No hay mensajes recientes en el canal que hablen sobre el precio del oro actualmente, pero puedo explicarte las razones generales por las que la onza de oro suele subir de precio:

Factores principales que impulsan el alza del oro

1. Incertidumbre econ?mica y geopol?tica

- El oro es considerado un "refugio seguro" (activo safe haven)
- En per?odos de tensi?n geopol?tica, guerras o inestabilidad pol?tica, los inversores buscan proteger su capital en metales preciosos

2. Expectativas sobre tasas de inter?s

- Cuando los bancos centrales (como la Reserva Federal de EE.UU.) reducen tasas o se esper

---

Did this answer your question?

NO

#### TEST 02:

Holger:
Cual es el precio actual de la onza de oro?

UPN Assistant:
No tengo informaci?n sobre el precio actual de la onza de oro en los mensajes recientes del canal.

Como los precios del oro fluct?an constantemente

---

Did this answer your question?

NO

If you can note, the user Holger is making questions to the bot called UPN Assistant. The questions are related with the last messages provided in the channel. In another words, the both questions had answer into the telegram channel messages, however, the bot was not capable to understand it (or maybe not process it), and the replies are wrong or we can interpret that was not considered the channel context. Please, improve the functionality of the system in order to can fix this trouble and provide much more precise answer. You can consider some another options like make the process of channel context extraction (from the most recently message until the 24 h before message) into some type of chache system and after retrieve it when some question is submited and the system need retrieve the context. Consider some efficient options in order to solve this problem. Also you can consider the possibility to implement some RAG, but remember that the RAG need to be dinamically updated conformed new messages are coming and also need to have a fast system of knowledge search. Thus, consider the posibilities and provide to me the most efficient in order to the LLM have the capacity to answer tailored with the question and the information provided in the telegram group as the priority context.

### 3RD ROUND OF SYSTEM PROMPTING: refactoring

take in account the project msg_assistant main folder of the structure of my project. Based on it, i want to you refactorize the entire code, taking in account the next instructions:

- the entire functionality is correctly done. We are just refactoring the folder and files structure of the project.

1) In the messages sent to the telegram bot or replied, take in account that the emoticons are not recognized, showing some characters like "?" or "??". I want you change it. Maybe consider the posibility of use markdown v2 or any other option which can read correctly the emoticons and the text inside of each message
2) the text of messages, telegram buttons or replies which you see that is managed in english langauge, translate it to the spanish language.
3) now you will adapt the code and update the location of some files according with the next set of modifications in the structure of project provided above:

- main folder: msg_assistant
- second level folder:
  data -> contains the files: channel_messages.json and subscribers.json
  rag -> contains the files: __init__.py, llm_client.py, channel_context.py and test.py
  settings -> contains the files: .env and config.py
  prompts -> contaisn the files: instruct.md and system.md
  handlers -> contains the files: broadcast_manager.py, escalation_manager.py and subscriber_manager.py
- files in first level:
  cmd.txt, bot.py, requirements.txt and README.md

4) take in account the description of modifications in the structure of the project, and move the files in the hierarchy structure of files mentioned before and indeed, if in the code is necessary make some modifications in the import or in the call of the classes or objects, also make all these necessary refactorization in order to the system maintains the functionality as the original system.
5) Don't change functionalities of the system. Just make strictly the modifications defined above in the description of prompt and explain me step by step what you are doing in order to achieve this goal
