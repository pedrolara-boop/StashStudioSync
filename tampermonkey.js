// ==UserScript==
// @name         Stash Studio Matcher Button
// @namespace    http://tampermonkey.net/
// @version      0.1
// @description  Add a Match Metadata button to studio pages
// @author       You
// @match        http://10.10.10.4:9999/studios/*/scenes*
// @grant        GM_xmlhttpRequest
// ==/UserScript==

(function() {
    'use strict';

    function logWithTime(message) {
        const time = new Date().toLocaleTimeString();
        console.log(`[${time}] ${message}`);
    }

    function addMatchButton() {
        const editContainer = document.querySelector('.details-edit');
        if (!editContainer || document.getElementById('match-metadata-btn')) return;

        const buttonWrapper = document.createElement('div');
        const matchButton = document.createElement('button');
        matchButton.id = 'match-metadata-btn';
        matchButton.className = 'btn btn-primary';
        matchButton.style.marginLeft = '0.5rem';
        matchButton.innerHTML = '<i class="fas fa-sync"></i> Match Metadata';

        buttonWrapper.appendChild(matchButton);
        editContainer.insertBefore(buttonWrapper, editContainer.querySelector('.delete'));

        matchButton.addEventListener('click', async () => {
            try {
                const studioId = window.location.pathname.split('/')[2];
                logWithTime(`Starting match for studio ID: ${studioId}`);
                
                matchButton.disabled = true;
                matchButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Matching...';

                const requestBody = {
                    query: `mutation RunPluginTask($plugin_id: ID!, $args: [PluginArgInput!]) {
                        runPluginTask(
                            plugin_id: $plugin_id,
                            task_name: "Force Update Single Studio",
                            args: $args
                        )
                    }`,
                    variables: {
                        plugin_id: "StashStudioMetadataMatcher",
                        args: [
                            {
                                key: "studio_id",
                                value: { str: studioId }
                            }
                        ]
                    }
                };

                logWithTime('Sending request:');
                logWithTime(JSON.stringify(requestBody, null, 2));

                const response = await fetch('http://10.10.10.4:9999/graphql', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestBody)
                });

                const result = await response.json();
                logWithTime('Full response:');
                logWithTime(JSON.stringify(result, null, 2));

                if (result.errors) {
                    console.error('GraphQL Errors:', result.errors);
                    throw new Error(result.errors[0].message);
                }

                if (result.data && result.data.runPluginTask) {
                    logWithTime(`Task ID: ${result.data.runPluginTask}`);
                    matchButton.innerHTML = '<i class="fas fa-check"></i> Success!';
                    // Wait 3 seconds before reload
                    setTimeout(() => {
                        window.location.reload();
                    }, 3000);
                } else {
                    logWithTime('No task ID in response');
                }

            } catch (error) {
                logWithTime(`Error: ${error.message}`);
                console.error('Detailed error:', error);
                matchButton.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
                matchButton.disabled = false;
                setTimeout(() => {
                    matchButton.innerHTML = '<i class="fas fa-sync"></i> Match Metadata';
                }, 3000);
            }
        });
    }

    // Check periodically for the edit container
    const checkInterval = setInterval(() => {
        if (document.querySelector('.details-edit')) {
            addMatchButton();
            clearInterval(checkInterval);
        }
    }, 500);
})();