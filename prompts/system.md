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

### 5TH ROUND OF SYSTEM PROMPTING: ADDING MULTIMODAL FEATURES

Currently, my system can process the text publications in the channel and store in the channel_messages.json for future processing of RAG in order to can have the capacity to answer questions.

However, now i want add a new functionality! In parallel (it means, completely independently from this currently project) i developed one system which can have the capacity of receive a multimedia content (1 image + 1 text together in the same post) in telegram channel, and make the ingestion, taking the image, storing in the image in some folder called multimedia and sending this to AI model kimi-k2.5 via API to make the transcript from this image and concatenating this text result with the text caption part of the multimodal post. The tecnical description of how this system was developed you can see in the file in this root here in this project:
@multimodal_requirements.md
Together with the documentation of this file multimodal_requirements.md, i will add the mentioned files in the documentation in order to you can have the source code guide of how it was implemented.

[here put the sequence of files corresponded of source code of project telegram_post_extraction]

- Now, you can analyze very deep this small independent project and now, adapt the same functionality to my project here msg_assistant. I want you accoplate this functionality, but respecting the structure OOP of this project and how it is organized need to maintain it homogeneously.
- Consider add some module in the project called ingest and inside manage all the part of ingest services corresponded of donwload the image and process the image, send to AI to obtain the transcript and concatenate it with the original caption text like was done also in the code provided above
- when the AI transcript of the image, together with the caption text was concatenated, you need to store this text result exactly like you do for the text publicacions in the file channel_messages.json
- the llm_client.py file continue managing the logic of prompt manager to answer the questions of the users, it's probable that it will not suffer no many changes. Take in account that we use the same model and the same LLM_API_KEY which we use in the independently telegram multimodal ingestor and in this project of msg_assistant
- In the project mentioned above, they manage the next .env variables:

API_ID =

API_HASH =

CHANNEL_USERNAME =

SESSION_NAME =

MEDIA_FOLDER =

LLM_API_KEY =

LLM_URL =

for us, when you will integrate the functionalities, consider that LLM_API_KEY, CHANNEL_USERNAME and LLM_URL are exactly the same, thus, you can reuse what we already implement here in our project in settings/config.py.

However API_ID, API_HASH  and SESSION_NAME are important variables for the TelegramClient, and you can manage it as class TelegramMultimodalListener in the settings/config.py if you consider conveniently when need extract the .env values and put in the class. The MEDIA_FOLDER you can manage just as simple global variable which contains the new folder "multimedia" (place which will stored all the images uploaded in the telegram channel)

- implement the functionalities with minimal changes in the software structure. Remember that modularization, and division of functionalities taking in account the good practices of OOP are priority. We cant maintain all the main functionalities of the system, we just want add a new functionality of multimodality processing of telegram messages. Probable some functionalities you will need add in the module handlers, like for example the message_handler.py which you can rename in more appropriate way as multimodal_msg_handler.py or something similar to this.
- read with attention the documentation in @beautifulMentionfile and take in account all my specifications in order to add this functionality to my system. I guess that not any modification is necessary do in queue_manager or in the rag processing. Provide to me the plan, the step by step execution, diagrams of interaction between components and documentation of the solution provided in some markdown file.

### 6TH ROUND OF PROMPTING: INTRODUCE SPEECH RECOGNITION MODULE

Now, i want integrate some system of speech transcription to this current system msg_assistant. In order to do this, i want to you make the next considerations:

1) read the file audio_transcription_system.md. This document contains the information related with the architecture ad features of some another implemented system called speech_text_queue.
2) the main idea is incorporate these caracteristics to our system in order to can be capable to recognize the audio files in format .ogg which the user can upload into the chat or the audios which the owner of the channel consider that can record and upload in the channel.
3) The functionalities related with the audio transcription which will need to be integrated in the system are these:

3.1 - in the channel:

- if the owner of the channel will record a audio and upload in the telegram channel, this file .ogg need to be stored in the folder multimedia/audio. The filename need to have a similar logic of the image name in the script ingest/vision/media_downloader.py. The name of the audio .ogg stored into the folder multimedia/audio, need contain the id of the message concatenated with the date and the extension of the file.
- After to be stored, start a process of ingest (all the scripts responsible by this process of downloader, ingest and audio transcriber need to write in the module ingest/speech in similar logic of organization like was done for the module ingest.vision). In this case we will use the NVIDIA whisper-large-v3 API and riva gRPC with persistent client (singleton), following the logic explained in the @beautifulMention.
- we need integrate the nvidia-riva library to our system. In order to do this, in our system, we need to apply:

$ git clone https://github.com/nvidia-riva/python-clients.git

for this, i want to you create a folder called "libraries" and put the python-clients folder and all this content inside of this folder "libraries"

- after make the transcription of the audio sent into the channel, i want to you store this textual transcript of audio into the data/channel_messages.json and also create a new text message into the channel showing the transcription message

3.2 - in the question interaction of the user with the bot

- in the question interaction with the bot, multiple users can use the service of send audio in concurrency, thus i want to you manage it using REDIS QUEUE to manage it. Take in account that we already have a queue to manage the question priority, but now i need the queue to manage the processing of audio into text consuming service of the NVIDIA API of whisper large-v3 model. This queue will manage this use of this audio transcription service efficiently with async workers taking the same parameters of the project speech_text_queue. However the database is another one (db:3). This redis queue will control and manage the use of audio transcription service, after that the text transcription generated from the audio need to store into the file questions.json.
- Play attention how you will organize the connection of this redis database and not confuse this with the currently queue_manager. The currently queue_manager is to manage the RAG process and attention of the question-answer order of priority according of the category of the question. Thus, we will have 2 queues with 2 different redis connections and 2 different redis databases. For more simple consideration, we can refactorize in the project msg_assistant queue_manager by queue_qa (making reference to this queue is for manage the question-answering process of RAG using redis database db:1) and the second queue manage the scripts into the some new folder called queue_speech and inside manage the scripts to can manage the use of the audio transcript service with gRPC client using redis database db:3.
- after some audio transcript from user question will done, need to store this transcription into the file questions.json. After that transcription as any question, the system need to show the buttons of the 4 categories of questions and the queue_qa will manage the priority of questions in the queue_qa and the response will need to be generated using the normal process using the textual transcription from the audio
- consider the next scripts from the project speech_text_queue as reference to can accoplate those functionalities tailored to my requirements for this current system msg_assistant together with the documentation in audio_transcription_system:

(scripts from the project speech_text_queue, which the logic will be userful to our project)

[the source code of project speech_text_queue]

- use the ideas of the scripts mentioned above (it is from the project speech_text_queue) and the documentation of ![](vscode-file://vscode-app/c:/Users/HP/AppData/Local/Programs/Antigravity/resources/app/extensions/theme-symbols/src/icons/files/markdown.svg)

audio_transcription_system.md to can apply the ideas of this project msg_assistant and integrate the functionality of audio transcription into the channel messages and into the private messages also. Make all this implementations, making the necessary refactorizations and also applying OOP good patterns practices and with correct division of functionalities and responsabilities. Provide to me the solution step by step and the whole picture of architecture and diagrams of functionality

You will need refactorize the functionality of ingest/speech/transcript_storage.py. The idea in this system is not store the transcripts in some separate file called data/transcripts.json, it isn't.

- The idea is after obtain the text transcription from the audio in the case of the audio message was uploaded in channel, the text transcription of this audio is store the message in channel_messages.json. And if the audio message was uploaded in private messages interactions with the bot, the text transcription of this audio is store the message in questions.json. After that, all the process of RAG for question-answering is treated by the rag as text.
- Remember that the questions are store using the script queue_qa/question_store.py through the class QuestionStore.
- Remember that the channel messages are store using the script rag/channel_context.py through the class ChannelContextManager

Please, refactorize the code taking in account this details. The process of ingestion have the unique responsability of trate the audio file, store it and make the process of transcription. Indeed, according with the responsabilities, the async_worker.py is more appropriate move to the folder  queue_speech.

### 7th ROUND OF PROMPTING: REFACTORIZING WhisperGRPC Client use

i want to you refactorize the project under the architecture :

ok, but the original idea was follow some architecture schema like this:

Multiple Clients (HTTP / App / Users)

    |

    v

Redis Job Queue

    |

    v

Async Worker Pool

    |

    v

Persistent gRPC Whisper Client (Singleton)

    |

    v

NVIDIA Whisper (Riva gRPC)

The current implementation doesn't follow the intented architecture yet.

The flow which i want is the next:

Workers ? [Persistent gRPC Client Singleton] ? NVIDIA Whisper

But the current implementation is running like this:

Workers ? [Subprocess] ? Script ? [New gRPC connection each time] ? NVIDIA Whisper

Thus i detected the next inefficiencies:

? Subprocess overhead per job
? No connection pooling
? Blocking I/O in async context
? The gRPC client singleton exists but is unused
? Authentication per job

- Taking in account the considerations above, i have a better idea. It's not much better send the instance of WhisperGRPCClient in grpc_client.py as object to the WhisperTranscriber into the ai_audio_transcriber.py script and delegate all the processing of transcribe to this class, mantaining the unique grpc instance as object in the WhisperTranscriber.
- Please, think about it in order to have much more splitted responsability. The idea of the grpc_client is build the connection, and ai_audio_transcriber is do the transcription operation. Please, if it is possible, refactorize according to this, but respecting the previous idea of do persistent grpc whisper client (singleton). The idea is have some schema of work like this:

Worker-1 ?

Worker-2 ?? [Persistent gRPC Client Singleton] ? NVIDIA

Worker-3 ?   (Single authenticated connection, reused by all workers)

- Indeed, dont forget please that we have the package python-clients and we need call the script:

SCRIPT_PATH=libraries/python-clients/scripts/asr/transcribe_file_offline.py

- Refactorize the program, prioritizing the efficiency of audio transcription task execution, the split of responsabilities and OOP design patters good practices

* Changes in the broadcast system reply for audio files

make some small changes in the process of broadcast. When the system detect some audio file, need to change the message broadcasted need constains the corresponded transcript text from the audio stored in the channel_messages.json. For example:

when i publish some audio in the channel, currently the result is this:

Example:
@Uuuuuujbff, tienes un nuevo mensaje importante!

Mensaje del canal:

---

Esta es una notificacion automatica del canal.

Now, take this example and formulate in the broadcast for audio images, put the corresponded text transcript stored in the file channel channel_messages.json

make small changes in the code respecting the OOP structure of the current project and the division of responsabilities and functionalities of each component of the system


### 8TH ROUND OF PROMPTING: SCALING TO 1 CONTAINER TELEGRAM BOT APP + 8 REPLICAS


ok, now taking as basis this solution, i want make some aclarations and i want to you fine-tune the architecture taking in account the next scenario:

1) i have 1 single server in production. This server will need run 9 containers (1 the original and 8 replicas)
2) each replica have different environment variables:

.env

#============================

# TELEGRAM CHANNEL SETTINGS |

#============================

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=
OWNER_USERNAME=
OWNER_CHAT_ID=

#=====================

# LLM MULTIMODAL API |

#=====================

LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
LLM_TEMPERATURE=
LLM_MAX_TOKENS=

#=====================

# MANAGERS SETTINGS  |

#=====================

BROADCAST_DELAY_HOURS=
BROADCAST_ENABLED=
CONTEXT_HOURS=
MAX_CONTEXT_MESSAGES=
LOG_LEVEL=

#=====================

# REDIS QUEUE - QA   |

#=====================

REDIS_HOST=
REDIS_PORT=
REDIS_DB=
REDIS_USERNAME=
REDIS_PASSWORD=
QUEUE_MAX_SIZE=
QUEUE_NUM_WORKERS=
QUEUE_MAX_RPM=
MEDIA_FOLDER=

#=====================

# SPEECH SYSTEM API  |

#=====================

SPEECH_API_KEY=
WHISPER_FUNCTION_ID=
WHISPER_SERVER=
LANGUAGE_CODE=
REDIS_SPEECH_DB=
REDIS_SPEECH_QUEUE=
MAX_SPEECH_WORKERS=
RIVA_LOCAL_URI=
SCRIPT_PATH=
SPEECH_FOLDER=

each container of telegram_bot replica (application) will have different configuration in the enviroment variables (it means, will have different TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, REDIS_DB, etc, etc...). However, the all the internal functionality of the bot is exaclty the same as the original container telegram_bot, changing just 2 aspects:

- environment variables configuration located in the folder settings/.env
- redis databases

3) redis databases: given the fact of the scalability, is desirable to me from now, manage 2 different instances of the redis (in point of view of infrastructure, it means 2 different redis containers and 2 different redis insight instances also). We will have 9 telegram bots each one in 1 different docker container. And also, each one will have 1 single database from each of our 2 docker redis database instance.

- 1st redis instance: redis_db_qa (docker container which will manage 9 databases: from db:0 until db:8), which will manage the redis priority queue for question-answering management
- 2nd redis instance: redis_db_speech (docker container which will manage 9 databases: from db:0 until db:8), which will manage the redis queue for speech transcription management

4) redisinsight instances: also 2 containers which will manage 1 container for redis_db_qa databases and 2nd container for redis_db_speech.
5) in another words, each application will have the next structure:

app_telegram_bot_00 :

+ 1 docker container for telegram_bot_0
+ 1 database from redis database container redis_db_qa: db:0
+ 1 database from redis database container redis_db_speech: db:0
+ 1 folder data with the own 3 files data: subscribers_0.json, channel_messages_0.json and questions_0.json
+ own file settings/.env with it's own configuration (same environment variables, but with different values)

app_telegram_bot_01:

+ 1 docker container for telegram_bot_1
+ 1 database from redis database container redis_db_qa: db:1
+ 1 database from redis database container redis_db_speech: db:1
+ 1 folder data with the own 3 files data: subscribers_1.json, channel_messages_1.json and questions_1.json
+ own file settings/.env with it's own configuration (same environment variables, but with different values)

....

app_telegram_bot_08:

+ 1 docker container for telegram_bot_8
+ 1 database from redis database container redis_db_qa: db:8
+ 1 database from redis database container redis_db_speech: db:8
+ 1 folder data with the own 3 files data: subscribers_8.json, channel_messages_8.json and questions_8.json
+ own file settings/.env with it's own configuration (same environment variables, but with different values)

6) all these containers will run in the same server. Thus in total in the server i will have 12 docker containers:

+ 9 docker containers for application: telegram_bot_00, telegram_bot_01, ... , telegram_bot_08
+ 2 docker containers for redis database: redis_db_qa and redis_db_speech
+ 2 docker containers for redis insight: redisinsight_qa and redisinsight_speech

---

TOTAL: 13 containers running in the same server

7) in the case of the docker containers for application, each telegram bot container is the exactly same replica in terms of functionality respect to the telegram_bot_00, differentiating by the .env file and configuration of values for each variable
8) in the case of each container in application, will need to have network connecting with the 2 containers of redis database (redis_db_qa and redis_db_speech), but calling to the numerical database respectively to the number of the telegram bot container (example telegram_bot_04, will connect with db:4 from redis_db_qa and db:4 from redis_db_speech and exacly the same for redis insight)
9) please consider the specifications defined here. Consider that i don't have a cluster (i work with the resources of 1 single server) and the computer resources of my server will manage and monitorize smartly. Thus, please think about this architecture solution proposed here, and if you think if exist a more efficient solution, propose me, and also if kubernetes can help me to manage this entire complexity more easily in order to put this system in production. Also consider that each telegram bot is independent, will have different data stored and will connect to different redis databases, but i want by preference manage an shared infrastructure. Think about it if it's a good solution, and if not, criticize it and propose to me a more optimal way.
10) provide to me a final solution as a engineer of infrastructure/devops, thinking that this system will deploy in production server and need run with the most efficient use as possible of my server resources. In the end, generate to me a one documentation file (in markdown format .md), with diagrams and explaining very deeply the proposed solution and the interaction between components
