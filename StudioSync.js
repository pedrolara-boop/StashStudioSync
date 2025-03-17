// StudioSync Button functionality
(function() {
    'use strict';

    // Utility functions
    function waitForElementClass(elementId, callBack, time) {
        time = (typeof time !== 'undefined') ? time : 100;
        window.setTimeout(() => {
            const element = document.getElementsByClassName(elementId);
            if (element.length > 0) {
                callBack(elementId, element);
            } else {
                waitForElementClass(elementId, callBack);
            }
        }, time);
    }

    function createElementFromHTML(htmlString) {
        const div = document.createElement('div');
        div.innerHTML = htmlString.trim();
        return div.firstChild;
    }

    const btnId = 'match-metadata-btn';
    
    async function matchStudio() {
        try {
            const studioId = window.location.pathname.split('/')[2];
            const button = document.getElementById(btnId);
            
            if (!button) return;
            
            // Disable button and show loading state
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Matching...';

            console.log('Attempting to match studio:', studioId);

            // Call the plugin task to update the studio
            const response = await fetch('/graphql', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: `
                        mutation RunPluginTask($plugin_id: ID!, $args: [PluginArgInput!]) {
                            runPluginTask(
                                plugin_id: $plugin_id,
                                task_name: "Match Studios",
                                args: $args
                            )
                        }
                    `,
                    variables: {
                        plugin_id: "StudioSync",
                        args: [
                            {
                                key: "studio_id",
                                value: { str: studioId }
                            },
                            {
                                key: "force",
                                value: { str: "true" }
                            },
                            {
                                key: "dry_run",
                                value: { str: "false" }
                            }
                        ]
                    }
                })
            });

            const result = await response.json();
            console.log('GraphQL Response:', result);

            if (result.errors) {
                console.error('GraphQL Errors:', result.errors);
                throw new Error(result.errors[0].message);
            }

            // Add delay before showing success
            await new Promise(resolve => setTimeout(resolve, 1000));

            // Show success state
            button.innerHTML = '<i class="fas fa-check"></i> Success!';
            
            // Log success message
            console.log('Studio match completed successfully');
            
            // Wait 5 seconds to show success state and ensure processing is complete, then reload
            setTimeout(() => {
                window.location.reload();
            }, 5000);

        } catch (error) {
            console.error('Error matching studio:', error);
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            const button = document.getElementById(btnId);
            if (button) {
                button.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error';
                button.disabled = false;
                
                // Reset button after 3 seconds
                setTimeout(() => {
                    button.innerHTML = '<i class="fas fa-sync"></i> Match Metadata';
                }, 3000);
            }
        }
    }

    function addStudioButton() {
        if (!window.location.pathname.includes('/studios/')) return;
        
        waitForElementClass('detail-header', function(className, elements) {
            if (!document.getElementById(btnId)) {
                const editContainer = elements[0].querySelector('.details-edit');
                if (!editContainer) return;

                const button = createElementFromHTML(`
                    <button id="${btnId}" class="btn btn-primary ml-3">
                        <i class="fas fa-sync"></i> Match Metadata
                    </button>
                `);
                
                button.onclick = matchStudio;
                
                // Insert before the delete button if it exists
                const deleteButton = editContainer.querySelector('.delete');
                if (deleteButton) {
                    editContainer.insertBefore(button, deleteButton);
                } else {
                    editContainer.appendChild(button);
                }
            }
        });
    }

    // Set up the observer to watch for page changes
    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            if (mutation.type === 'childList') {
                addStudioButton();
            }
        }
    });

    // Start observing the document with the configured parameters
    observer.observe(document.body, { childList: true, subtree: true });

    // Also try to add the button immediately in case we're already on a studio page
    addStudioButton();
})(); 