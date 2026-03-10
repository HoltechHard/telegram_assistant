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
    	 |
	 v
Bot: [Processes with channel context]
  	 |
	 v
Bot: "Based on the channel announcement, the meeting was..."
	  |
	  v
[Shows YES/NO buttons]
	  |
	  v
User clicks YES  -->  Marked as resolved
User clicks NO  --> Escalated to owner

It is supossed that the bot will process the answer according to the channel context. Is supossed that the context collection is obtained in the next logic:

Channel --> Fetch Messages (24h)  -->  Cache -->  LLM Context
                                    |
	 			    v
                            TTL: 5 minutes

So, now i submit into test the system. The owner send the next 2 messages to the telegram channel (information related with the current price of the gold):

---- channel messages ------

[3/3/2026 11:59 AM] UPN CHANNEL: El precio del oro experimenta fluctuaciones este 3 de marzo de 2026, manteniendose por encima de los 5.300 dolares por onza en el mercado internacional. Tras un repunte reciente impulsado por tensiones geopol?ticas en Oriente Medio (incluyendo acciones de EE.UU. e Israel contra Iran), el oro spot cotiza alrededor de 5.310-5.330 USD/onza, con ligeras correcciones por un dolar mas fuerte y mayores rendimientos de bonos.
[3/3/2026 3:48 PM] UPN CHANNEL: El metal precioso supera los US$ 5.400 por onza ante la intensificacion del conflicto entre Iran, Estados Unidos e Israel. La volatilidad geopolitica y el riesgo sobre las rutas de suministro impulsan la demanda por activos refugio.
El precio del oro alcanza este lunes su nivel mas alto en un mes, extendiendo el rally iniciado la semana pasada en medio de la escalada del conflicto en Medio Oriente. El metal llega a subir hasta 2,9%, superando los US$ 5.400 por onza, antes de moderar parte de sus ganancias con la apertura de los mercados en Estados Unidos.

And then, the users make the next interactions with the bot (questions):

#### TEST 01:

Holger:
Porque motivo el precio de la onza de oro esta subiendo?

UPN Assistant:
No hay mensajes recientes en el canal que hablen sobre el precio del oro actualmente, pero puedo explicarte las razones generales por las que la onza de oro suele subir de precio:

Factores principales que impulsan el alza del oro

1. Incertidumbre economica y geopolitica

- El oro es considerado un "refugio seguro" (activo safe haven)
- En periodos de tension geopolitica, guerras o inestabilidad politica, los inversores buscan proteger su capital en metales preciosos

2. Expectativas sobre tasas de interes

- Cuando los bancos centrales (como la Reserva Federal de EE.UU.) reducen tasas o se esper

---

Did this answer your question?

NO

#### TEST 02:

Holger:
Cual es el precio actual de la onza de oro?

UPN Assistant:
No tengo informacion sobre el precio actual de la onza de oro en los mensajes recientes del canal.

Como los precios del oro fluctuan constantemente

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

### 4TH ROUND OF SYSTEM PROMPTING: adding functionalities

Consider the last version of this telegram assistant project. And now, i want to you make some updates respect the queue implemented to manage the order of user questions:

- consider this draft idea of architecture to add to this system:

Telegram Updates
        |
        v
Async Handler (fast)
        |
        v
Admission Control (queue limit)
        |
        v
Priority Queue
        |
        v
Worker Pool (N workers)
        |
        v
LLM Execution
        |
        v
Response Sender

The idea is help to telegram bot can scale the use to attent a high number of users in good and efficient way. To this, we will implement a redis queue under this logic:

1) the user make the question, and under this question, the bot send a automatic question in the chat with 4 buttons options which the user need press to categorize the type of question before proceed the processing.
   bot question: Qual categoria de pregunta tienes?
   telegram buttons:

- Notas
- Evaluaciones
- Tareas
- Otros

2) After the user press some button, automatically, the system will store this question in some json file (question_id: automatic field, question_description: the formulated question by the user, category: the button pressed category, status: true if is already attend or false if it is not attent by the telegram bot yet) and in redis database store in efficient way in order to can use the redis database to manage a priority queue. Make some optimizations in order to can make a efficient attention of this queue and if it is possible with parallelization and concurrency. Also for this consider that my server have these capabilities:

- 1 vCPU core
- 4 GB RAM
- 50 GB NVMe disk space
- 4 TB bandwidth

3) In the priority queue, manage the priority according to 2 criteria:

- 1st one: category of question (according to the field of category, notas =1, evaluaciones = 2, tareas = 3, otros = 4), smallest score is higher level of priority
- 2nd one: if have draw, apply FIFO (first comes, first which is attent)

4) Taking in account the capabilities of the server and also the limitation of LLM API of maximum 10 RPM (requests per minute of limit via the API), adopt efficient modifications in the project in order to maximize the efficiency of computer resources and consider that i want scale in number of users and message requests, so it's good idea fit the system to can  make the best use as possible of the computational resources of the server. The idea is build a system with no so high delay in the process of answering messages
5) provide to me the step by step solution to fix these functional requirements (the number of users not exceed of 50 and replies in concurrency maybe is less than 5 in spike moments)
