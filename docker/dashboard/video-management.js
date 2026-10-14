function initRemoteStreams(api) {
    const remoteStreamsElement = document.getElementById("remote-streams");

    const listener = {
      producerAdded: function (producer) {
        const producerId = producer.id
        console.log("producer added", producer.meta.name);
        if (producer.meta.name != "robot") {
          return;
        }

        if (!document.getElementById(producerId)) {
          remoteStreamsElement.insertAdjacentHTML("beforeend",
            `<li id="${producerId}">
                              <div class="button">connect</div>
                              <div class="flex-container-row">
                                <div class="video">
                                    <div class="spinner">
                                        <div></div>
                                        <div></div>
                                        <div></div>
                                        <div></div>
                                    </div>
                                    <span class="remote-control">&#xA9;</span>
                                    <video></video>
                                    <div class="fullscreen"><span title="Toggle fullscreen">&#x25A2;</span></div>
                                </div>
                                <div class="video">
                                    <div class="spinner">
                                        <div></div>
                                        <div></div>
                                        <div></div>
                                        <div></div>
                                    </div>
                                    <span class="remote-control">&#xA9;</span>
                                    <video></video>
                                    <div class="fullscreen"><span title="Toggle fullscreen">&#x25A2;</span></div>
                                </div>
                              </div>
                          </li>`);

          const entryElement = document.getElementById(producerId);
          const videoElement = entryElement.getElementsByTagName("video")[0];
          const videoRightElement = entryElement.getElementsByTagName("video")[1];

          videoElement.addEventListener("playing", () => {
            if (entryElement.classList.contains("has-session")) {
              entryElement.classList.add("streaming");
            }
          });

          videoRightElement.addEventListener("playing", () => {
            if (entryElement.classList.contains("has-session")) {
              entryElement.classList.add("streaming");
            }
          });

          entryElement.addEventListener("click", (event) => {
            event.preventDefault();
            if (!event.target.classList.contains("button")) {
              return;
            }

            if (entryElement._consumerSession) {
              entryElement._consumerSession.close();
            } else {
              const session = api.createConsumerSession(producerId);
              if (session) {
                entryElement._consumerSession = session;

                session.addEventListener("error", (event) => {
                  if (entryElement._consumerSession === session) {
                    console.error(event.message, event.error);
                  }
                });

                session.addEventListener("closed", () => {
                  if (entryElement._consumerSession === session) {
                    videoElement.pause();
                    videoElement.srcObject = null;
                    videoRightElement.pause();
                    videoRightElement.srcObject = null;
                    entryElement.classList.remove("has-session", "streaming", "has-remote-control");
                    delete entryElement._consumerSession;
                  }
                });

                session.addEventListener("streamsChanged", () => {
                  if (entryElement._consumerSession === session) {
                    const streams = session.streams;
                    console.log("nb streams", streams.length);
                    if (streams.length > 0) {
                      // Left view and audio
                      videoElement.srcObject = streams[0];
                      videoElement.play().catch(() => { });

                      const originalStream = streams[0];
                      let desiredVideoTrack = null;

                      let nb_video_tracks = 0;
                      // We consider two tracks maximum, the right view being the second one
                      originalStream.getTracks().forEach((track) => {
                        if (track.kind === 'video') {
                          desiredVideoTrack = track;
                          nb_video_tracks++;
                        }
                      });

                      if (desiredVideoTrack && nb_video_tracks > 1) {
                        const newStream = new MediaStream([desiredVideoTrack]);
                        videoRightElement.srcObject = newStream;
                        videoRightElement.play().catch(() => { });
                      } else {
                        console.warn("No video track found in the stream.");
                      }

                    }
                  }
                });

                session.addEventListener("remoteControllerChanged", () => {
                  if (entryElement._consumerSession === session) {
                    const remoteController = session.remoteController;
                    if (remoteController) {
                      entryElement.classList.add("has-remote-control");
                      remoteController.attachVideoElement(videoElement);
                    } else {
                      entryElement.classList.remove("has-remote-control");
                    }
                  }
                });

                entryElement.classList.add("has-session");
                session.connect();
              }
            }
          });
        }
      },

      producerRemoved: function (producer) {
        const element = document.getElementById(producer.id);
        if (element) {
          if (element._consumerSession) {
            element._consumerSession.close();
          }

          element.remove();
        }
      }
    };

    api.registerProducersListener(listener);
    for (const producer of api.getAvailableProducers()) {
      listener.producerAdded(producer);
    }
  }

getOrbbecRGB = () => {
    const url = '/api/video/orbbec';

    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error('Orbbec error');
            }
            return response.json();
        })
        .then(data => {
            document.getElementById('videoCard-title').textContent = 'Camera view';
            document.getElementById('head-view-tab').disabled = false;
            const torsoTab = document.getElementById('torso-view-tab');
            torsoTab.disabled = false;
            torsoTab.textContent = 'Torso';
            const imageElement = document.getElementById('orbbec-image');
            imageElement.src = `data:image/jpeg;base64,${data.rgb}`;
            imageElement.alt = 'Orbbec Camera Image';
            const depthElement = document.getElementById('orbbec-depth');
            depthElement.src = `data:image/jpeg;base64,${data.depth}`;
            depthElement.alt = 'Orbbec Camera Depth Image';
        })
        .catch(error => {
            // The torso's ROS image endpoint is independent of head WebRTC.
            document.getElementById('videoCard-title').textContent = 'Camera view';
            document.getElementById('head-view-tab').disabled = false;
            const torsoTab = document.getElementById('torso-view-tab');
            torsoTab.disabled = true;
            torsoTab.textContent = 'Torso (unavailable)';
            if (document.getElementById('torso-view').classList.contains('active')) {
                showTab('head-view');
            }
            console.warn('Torso camera unavailable:', error);
        });
}

//////////////////////////////
// Handling tab switching between head and torso camera views
function showTab(tabId) {
    document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    document.querySelector(`.tab[onclick="showTab('${tabId}')"]`).classList.add('active');
    document.getElementById(tabId).classList.add('active');
  }