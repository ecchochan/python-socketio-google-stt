


import socketio
import asyncio
import json
import threading
from six.moves import queue
from google.cloud import speech_v1p1beta1 as speech
from google.cloud.speech_v1p1beta1 import types
from google.protobuf.json_format import MessageToDict
import os


# Get one from https://console.cloud.google.com/apis/credentials
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '' 


import socketio

mgr = socketio.AsyncRedisManager('redis://')
sio = socketio.AsyncServer(client_manager=mgr,cors_allowed_origins=[])

// sio = socketio.AsyncServer(async_mode='aiohttp', async_handlers=True)
                           
                           
                           
sio.attach(app)

sessions = {}

def get_session(sid):
    if sid not in sessions:
        sessions[sid] = {}
    return sessions[sid]
    


class Transcoder(object):
    """
    Converts audio chunks to text
    """
    def __init__(self, 
                 encoding, 
                 rate, 
                 language, 
                 async_callback,
                 context = "", 
                 model = "command_and_search", # command_and_search
                 single_utterance=False,
                 use_enhanced=False,
                 interim_results=True,
                 metadata={}):
        self.buff = queue.Queue()
        self.encoding = encoding
        self.language = language
        self.rate = rate
        self.transcript = None
        self.model= model
        self.context = context
        self.interim_results = interim_results
        self.single_utterance = single_utterance
        self.async_callback = async_callback
        self.terminated = False
        self.metadata = metadata

    def start(self):
        """Start up streaming speech call"""
        threading.Thread(target=self.process, args=(asyncio.new_event_loop(),)).start()

        
    def response_loop(self, responses):
        """
        Pick up the final result of Speech to text conversion
        """
        for response in responses:
            if not response.results:
                continue
            result = response.results[0]
            if not result.alternatives:
                continue
            transcript = result.alternatives[0].transcript
            
            if result.is_final:
                self.transcript = transcript
                print(transcript)
                
    def process(self, loop):
        """
        Audio stream recognition and result parsing
        """
        #You can add speech contexts for better recognition
        cap_speech_context = types.SpeechContext(**self.context)
        metadata = types.RecognitionMetadata(**self.metadata)
        client = speech.SpeechClient()
        config = types.RecognitionConfig(
            encoding=self.encoding,
            sample_rate_hertz=self.rate,
            language_code=self.language,
            speech_contexts=[cap_speech_context,],
            enable_automatic_punctuation=True,
            model=self.model,
            metadata=metadata
        )
        
        streaming_config = types.StreamingRecognitionConfig(
            config=config,
            interim_results=self.interim_results,
            single_utterance=self.single_utterance)
        audio_generator = self.stream_generator()
        requests = iter(types.StreamingRecognizeRequest(audio_content=content)
                    for content in audio_generator)

        responses = client.streaming_recognize(streaming_config, requests)
        #print('process',type(responses))
        try:
            #print('process')
            for response in responses:
                #print('process received')
                if self.terminated:
                    break
                if not response.results:
                    continue
                result = response.results[0]
                if not result.alternatives:
                    continue
                speechData = MessageToDict(response)
                global_async_worker.add_task(self.async_callback(speechData))
                
                # debug
                transcript = result.alternatives[0].transcript

                #print('>>', transcript, "(OK)" if result.is_final else "")
        except Exception as e:
            print('process excepted', e)
            self.start()

    def stream_generator(self):
        while not self.terminated:
            chunk = self.buff.get()
            if chunk is None:
                return
            if self.terminated:
                break
            yield chunk

    def write(self, data):
        """
        Writes data to the buffer
        """
        self.buff.put(data)




    
@sio.on('startGoogleCloudStream')
async def startGoogleCloudStream(sid, args):
    session = get_session(sid)
    print('startGoogleCloudStream...')
    
    async def async_callback(data):
        await sio.emit('speechData', data, room=sid)
    
    config = args['config']
    metadata = args['metadata']
    
    transcoder = Transcoder(
        encoding=config["format"],
        rate=config["rate"],
        language=config["language"],
        async_callback=async_callback,
        context=config.get("context"),
        use_enhanced=config.get("use_enhanced", False),
        model=config.get("model", "command_and_search"),
        metadata=metadata
        
    )
    session['recognizeStream'] = transcoder
    transcoder.start()
    

@sio.on('endGoogleCloudStream')
async def endGoogleCloudStream(sid, args):
    session = get_session(sid)
    if 'recognizeStream' in session:
        session['recognizeStream'].terminated = True
        
        del session['recognizeStream']

    
    

@sio.on('binaryData')
async def binaryData(sid, args):
    session = get_session(sid)
    #print('streaming...')
    if 'recognizeStream' in session:
        session['recognizeStream'].write(args)



@sio.on('debug')
async def debug(sid, args):
    print('DEBUG::', args)



import sys

@sio.event
async def connect(sid, environ):
    print('Client connected ' + sid, file=sys.stderr)
    
@sio.event
async def disconnect(sid):
    print('Client disconnected ' + sid, file=sys.stderr)

ssl_context = None

if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=9003, ssl_context=ssl_context)

