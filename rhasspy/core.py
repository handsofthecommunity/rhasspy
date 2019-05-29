import os
import sys
import logging
import subprocess
from typing import List, Dict, Optional, Any, Callable, Tuple, Union

import pydash

# Internal imports
from .actor import ConfigureEvent, ActorSystem, RhasspyActor
from .profiles import Profile
from .audio_recorder import AudioData, StartRecordingToBuffer, StopRecordingToBuffer
from .stt import WavTranscription
from .intent import IntentRecognized
from .intent_handler import IntentHandled
from .pronounce import WordPronunciations, WordPhonemes, WordSpoken
from .tts import SentenceSpoken
from .dialogue import (
    DialogueManager,
    GetMicrophones,
    TestMicrophones,
    ListenForCommand,
    ListenForWakeWord,
    WakeWordDetected,
    WakeWordNotDetected,
    TrainProfile,
    ProfileTrainingFailed,
    GetWordPhonemes,
    SpeakWord,
    GetWordPronunciations,
    TranscribeWav,
    PlayWavData,
    PlayWavFile,
    RecognizeIntent,
    HandleIntent,
    ProfileTrainingComplete,
    ProfileTrainingFailed,
    MqttPublish,
    GetVoiceCommand,
    VoiceCommand,
    GetActorStates,
    GetSpeakers,
    SpeakSentence,
    GetProblems,
    Problems,
)

# -----------------------------------------------------------------------------


class RhasspyCore:
    """Core class for Rhasspy functionality."""

    def __init__(
        self,
        profile_name: str,
        system_profiles_dir: str,
        user_profiles_dir: str,
        actor_system: Optional[ActorSystem] = None,
    ) -> None:

        self._logger = logging.getLogger(self.__class__.__name__)
        self.profiles_dirs: List[str] = [user_profiles_dir, system_profiles_dir]
        self.profile_name = profile_name
        self.actor_system = actor_system

        self.profile = Profile(
            self.profile_name, system_profiles_dir, user_profiles_dir
        )
        self._logger.debug(f"Loaded profile from {self.profile.json_path}")
        self._logger.debug(
            f"Profile files will be written to {self.profile.write_path()}"
        )

        self.defaults = Profile.load_defaults(system_profiles_dir)

    # -------------------------------------------------------------------------

    def start(
        self,
        preload: Optional[bool] = None,
        block: bool = True,
        timeout: float = 60,
        observer: Optional[RhasspyActor] = None,
    ) -> None:
        """Start Rhasspy"""

        if self.actor_system is None:
            self.actor_system = ActorSystem()

        if preload is None:
            preload = self.profile.get("rhasspy.preload_profile", False)

        assert self.actor_system is not None
        self.dialogue_manager = self.actor_system.createActor(DialogueManager)
        with self.actor_system.private() as sys:
            sys.ask(
                self.dialogue_manager,
                ConfigureEvent(
                    self.profile,
                    preload=preload,
                    ready=block,
                    transitions=False,
                    load_timeout_sec=30,
                    observer=observer
                ),
            )

            # Block until ready
            if block:
                result = sys.listen(timeout)

    # -------------------------------------------------------------------------

    def get_microphones(self, system: Optional[str] = None) -> Dict[Any, Any]:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, GetMicrophones(system))
            assert isinstance(result, dict)
            return result

    def test_microphones(self, system: Optional[str] = None) -> Dict[Any, Any]:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, TestMicrophones(system))
            assert isinstance(result, dict)
            return result

    def get_speakers(self, system: Optional[str] = None) -> Dict[Any, Any]:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, GetSpeakers(system))
            assert isinstance(result, dict)
            return result

    # -------------------------------------------------------------------------

    def listen_for_wake(self) -> None:
        assert self.actor_system is not None
        self.actor_system.tell(self.dialogue_manager, ListenForWakeWord())

    def listen_for_command(self, handle: bool = True) -> Dict[str, Any]:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, ListenForCommand(handle=handle))
            assert isinstance(result, dict)
            return result

    def record_command(self, timeout: Optional[float] = None) -> VoiceCommand:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, GetVoiceCommand(timeout=timeout))
            assert isinstance(result, VoiceCommand)
            return result

    # -------------------------------------------------------------------------

    def transcribe_wav(self, wav_data: bytes) -> WavTranscription:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(
                self.dialogue_manager, TranscribeWav(wav_data, handle=False)
            )
            assert isinstance(result, WavTranscription)
            return result

    def recognize_intent(self, text: str) -> IntentRecognized:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, RecognizeIntent(text, handle=False))
            assert isinstance(result, IntentRecognized)

            # Add slots
            intent_slots = {}
            for ev in result.intent.get("entities", []):
                intent_slots[ev["entity"]] = ev["value"]

            result.intent["slots"] = intent_slots

            return result

    def handle_intent(self, intent: Dict[str, Any]) -> IntentHandled:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, HandleIntent(intent))
            assert isinstance(result, IntentHandled)
            return result

    # -------------------------------------------------------------------------

    def start_recording_wav(self, buffer_name: str = "") -> None:
        assert self.actor_system is not None
        self.actor_system.tell(
            self.dialogue_manager, StartRecordingToBuffer(buffer_name)
        )

    def stop_recording_wav(self, buffer_name: str = "") -> AudioData:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = self.actor_system.ask(
                self.dialogue_manager, StopRecordingToBuffer(buffer_name)
            )
            assert isinstance(result, AudioData)
            return result

    # -------------------------------------------------------------------------

    def play_wav_data(self, wav_data: bytes) -> None:
        assert self.actor_system is not None
        self.actor_system.tell(self.dialogue_manager, PlayWavData(wav_data))

    def play_wav_file(self, wav_path: str) -> None:
        assert self.actor_system is not None
        self.actor_system.tell(self.dialogue_manager, PlayWavFile(wav_path))

    # -------------------------------------------------------------------------

    def get_word_pronunciations(
        self, words: List[str], n: int = 5
    ) -> WordPronunciations:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, GetWordPronunciations(words, n))
            assert isinstance(result, WordPronunciations)
            return result

    def get_word_phonemes(self, word: str) -> WordPhonemes:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, GetWordPhonemes(word))
            assert isinstance(result, WordPhonemes)
            return result

    def speak_word(self, word: str) -> WordSpoken:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, SpeakWord(word))
            assert isinstance(result, WordSpoken)
            return result

    def speak_sentence(self, sentence: str) -> SentenceSpoken:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, SpeakSentence(sentence))
            assert isinstance(result, SentenceSpoken)
            return result

    # -------------------------------------------------------------------------

    def train(
        self, reload_actors: bool = True
    ) -> Union[ProfileTrainingComplete, ProfileTrainingFailed]:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(
                self.dialogue_manager, TrainProfile(reload_actors=reload_actors)
            )
            assert isinstance(result, ProfileTrainingComplete) or isinstance(
                result, ProfileTrainingFailed
            )
            return result

    # -------------------------------------------------------------------------

    def mqtt_publish(self, topic: str, payload: bytes) -> None:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            sys.tell(self.dialogue_manager, MqttPublish(topic, payload))

    # -------------------------------------------------------------------------

    def wakeup_and_wait(self) -> Union[WakeWordDetected, WakeWordNotDetected]:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, ListenForWakeWord())
            assert isinstance(result, WakeWordDetected) or isinstance(
                result, WakeWordNotDetected
            )

            return result

    # -------------------------------------------------------------------------

    def get_actor_states(self) -> Dict[str, str]:
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, GetActorStates())
            assert isinstance(result, dict)
            return result

    # -------------------------------------------------------------------------

    def send_audio_data(self, data: AudioData) -> None:
        assert self.actor_system is not None
        self.actor_system.tell(self.dialogue_manager, data)

    # -------------------------------------------------------------------------

    def shutdown(self) -> None:
        # Clear environment variables
        rhasspy_vars = [v for v in os.environ if v.startswith("RHASSPY")]

        for v in rhasspy_vars:
            del os.environ[v]

        # Stop actor system
        if self.actor_system is not None:
            self.actor_system.shutdown()
            self.actor_system = None

    # -------------------------------------------------------------------------

    def check_profile(self) -> bool:
        """Returns (True, output) if the profile has all necessary files downloaded."""
        check_path = self.profile.read_path("check-profile.sh")
        assert os.path.exists(check_path), "Missing profile check script"

        check_cmd = ["bash", check_path, self.profile.write_path()]

        # Only check embeddings if flair is being used
        if self.profile.get("intent.system", "") != "flair":
            check_cmd.append("--no-flair")

        self._logger.debug(check_cmd)

        try:
            subprocess.run(check_cmd, stderr=sys.stderr, stdout=sys.stderr, check=True)
        except subprocess.CalledProcessError as e:
            return False

        return True

    # -------------------------------------------------------------------------

    def download_profile(self, delete=False) -> None:
        """Downloads all necessary profile files from Github."""
        download_script = os.path.abspath(self.profile.read_path("download-profile.sh"))
        assert os.path.exists(download_script), "Profile download script is missing."
        download_cmd = ["bash", download_script, self.profile.write_path()]

        if delete:
            download_cmd.append("--delete")

        # Only download embeddings if flair is being used
        if self.profile.get("intent.system", "") != "flair":
            download_cmd.append("--no-flair")

        self._logger.debug(download_cmd)

        subprocess.run(download_cmd, stderr=sys.stderr, stdout=sys.stderr, check=True)

    # -------------------------------------------------------------------------

    def get_problems(self) -> Dict[str, Any]:
        """Returns a dictionary with problems from each actor."""
        assert self.actor_system is not None
        with self.actor_system.private() as sys:
            result = sys.ask(self.dialogue_manager, GetProblems())
            assert isinstance(result, Problems)
            return result.problems
