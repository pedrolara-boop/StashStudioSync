// Studio Matcher Button functionality
(function() {
    'use strict';

    const {
        stash,
        Stash,
        waitForElementId,
        waitForElementClass,
        waitForElementByXpath,
        getElementByXpath,
        sortElementChildren,
        createElementFromHTML,
    } = window.stash7dJx1qP;

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
                        plugin_id: "StashStudioMetadataMatcher",
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
            
            // Wait 3 seconds to show success state and ensure processing is complete, then reload
            setTimeout(() => {
                window.location.reload();
            }, 3000);

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

    // Add button when on studio page
    stash.addEventListener('page:studio:any', function() {
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
    });
})(); 