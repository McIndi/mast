jQuery.fn.outerHTML = function() {
   return (this[0]) ? this[0].outerHTML : '';
};

$.subscribe("modifyAppliances", function(event, appliances){
    // var warning = "<b>Warning, if you start a session here and add or remove an appliance above then your session will be erased and you will not be able to retrieve your transcript without serious effort in parsing the logs. This is a known issue and will be fixed, when it is this message will be removed.</b><br />";
    console.log( "Appliances were modified, rebuilding sshTerminals" );
    // sshTextbox template
    var sshTextbox = "<input type='textbox' name='sshCommand' size='80' /><input type='button' name='sshCommandButton' value='Issue Command' />";

    // sshTerminal template
    var sshTerminal = "<hr /><div id='ssh_<%id%>'><%id%><a href='#' class='sshTranscript' id='download_<%id%>'> download transcript </a><br /><textarea name='textarea_<%id%>' rows='20' cols='20'></textarea></div>";

    // initialize variables
    var htm2 = [];
    var content = {};

    $.each(environment.appliances, function(index, appliance){
        console.log("building terminal for appliance " + appliance.hostname);
        // create the id selecotor. hostname must be sanitized for JQuery
        var id = "#ssh_" + appliance.hostname.replace( /(:|\.|\[|\])/g, "\\$1" );

        // check if a sshTerminal already exists, and if so take the contents
        // and include them in the new html
        if ( $( id ).length ){
            // sshTerminal exists for this appliance
            // get content and append to the html array
            content[id] = $( id ).find( "textarea" ).val();
            htm2.push( "<hr />" + $( id ).outerHTML() )
        } else {
            // sshTerminal for this appliance does not exist
            // push a fresh sshTerminal template to the html array
            htm2.push(sshTerminal.replace(/<%id%>/g, appliance.hostname));
        }
    });
    console.log("html built " + sshTextbox + htm2.join(" "));
    // Replace the html in the "#mast\.datapower\.ssh" element with the freshly built html
    $("#mast\\.datapower\\.ssh").html( sshTextbox + htm2.join(" ") );
    // Scroll to the bottom of each sshTerminal
    $.each( content, function( id, cont ){
        var textarea = $( "#mast\\.datapower\\.ssh" ).find( id ).find( "textarea" )
        textarea.val( cont );
        textarea.scrollTop(textarea[0].scrollHeight - textarea.height());
    } );
});

// event handler for clicking on the "download transcript" link
$("#mast\\.datapower\\.ssh").on("click", ".sshTranscript", function( event ){
    // Prevent the browser from trying to open the href as a link
    event.preventDefault();
    target = $(event.target);
    // parent will contain the textarea as well as the link
    parent = target.parent();
    // get the content and hostname and copy them into variable
    data = {
        "content": parent.find( "textarea" ).val(),
        "hostname": parent.attr("id").replace( /ssh_/g, "" )
    }
    // POST the data to "/download" which will prompt a download of the data
    // converted to a text file
    $.download("/download", data, "POST");
});

// Event handler for clicking the "Issue Command" button
$("#mast\\.datapower\\.ssh").on("click", "input[name=sshCommandButton]", function(event){
    console.log("Issuing command")
    // Get the value in the textbox
    command = $("input[name='sshCommand']").val();
    console.log("command found " + command)
    // Empty the textbox
    $('input[name="sshCommand"]').val("");

    // initialize variables
    var appliances = [];
    var credentials = [];
    // loop through the appliances and see if the checkbox is checked
    $.each(environment.appliances, function(index, appliance){
        console.log("checking if " + appliance.hostname + " is selected")
        hostname = appliance.hostname;
        if($("input[type='checkbox'][name='"+hostname+"']").is(":checked")){
            // the checkbox is checked, add the hostname and obfuscate
            // the credentials
            appliances.push(hostname);
            credentials.push(xor.encode(appliance.credentials, xor.encode(getCookie("9x4h/mmek/j.ahba.ckhafn"), "_")));
            console.log(appliance.hostname + " is selected")
        }
    });
    // Get the "ephemeral session"
    ssh_session = $( "input[name='ephemeral_session']" ).val();
    console.log( "Ephemeral session " + ssh_session )

    // send the command along with the hostnames, ofuscated credentials
    // and the "ephemeral session" key
    data = {
        "command": command,
        "appliances": appliances,
        "credentials": credentials,
        "ssh_session": ssh_session
    };
    $.post('/ssh', data, function( _data ){
        $.each(environment.appliances, function(index, appliance){
            hostname = appliance.hostname;
            if($( "input[type='checkbox'][name='"+hostname+"']" ).is(":checked")){
                // if checkbox is checked (This could result in a race condition
                // if you check/uncheck boxes while issuing a command)

                // get the content of the sshTranscript for hostname
                var content = $("textarea[name='textarea_"+hostname+"']").val();
                console.log( "content built " + content )
                // set the content of textarea to the current value plus the
                // new data (ssh response)
                $("textarea[name='textarea_"+hostname+"']").val( content + _data[hostname] );

                // Scroll to bottom of the textarea
                var psconsole = $("textarea[name='textarea_" + hostname + "']");
                if( psconsole.length ){
                    psconsole.scrollTop(psconsole[0].scrollHeight - psconsole.height());
                }
            }
        });
    });
});

// Event handler to allow you to press enter when typing a command into the
// textbox
$("#mast\\.datapower\\.ssh").on("keypress", 'input[name="sshCommand"]', function(e) {
        if (e.keyCode == 13) {
            $("input[name=sshCommandButton]").trigger("click");
        }
});

