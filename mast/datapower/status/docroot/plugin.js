$.get("/config/status", function( data ){
    window.charts = {}
    var config=data;

    var randomColor = function(){
		var color = '#'+Math.floor(Math.random()*16777215).toString(16);
		
		console.log("Color:  " + color)
        return color;
    };

    var sanitize_provider = function( provider ){
        return provider.replace( /(:|\.|\[|\])/g, "\\$1" );
    };

    var get_chart_width = function(){
        var windowWidth = $( window ).width().toString();
        var chartWidth = windowWidth - (windowWidth/10);
        return chartWidth.toString() + "px";
    }

    var initialize_chart = function( provider ){

        if ( environment.appliances.length === 0){
            return
        }

        var el = $( "#status_main" );
        var template = '<div class="bordered" id="status_%provider%_container"><h2>%provider%</h2><canvas id="status_%provider%" width="%width%" height="200"></canvas><div id="status_%provider%_legend"></div></div>'
        var html = template.replace( /%provider%/g, provider );
        html = html.replace( /%width%/g, get_chart_width() );

        // Remove old chart
        var _provider = sanitize_provider( provider );
        $( "#status_" + _provider + "_container" ).remove();
        el.append( html );

        var datasets = [];
        $.each(environment.appliances, function(index, appliance){
			console.log("Color: " + config.colors[appliance.hostname])
            datasets.push({
                "label": appliance.hostname,
                "borderColor": config.colors[appliance.hostname],
                "data": []
            });
        });

        var ctx = $( "#status_" + _provider ).get(0).getContext("2d");
        var chart = new Chart(ctx, {
			"type": "line",
			"data": {
				"labels": [],
				"datasets": datasets
			},
			"options": {
				color: "#FFFFFF",
				plugins: {
					legend: {
						labels: {
							color: "#FFFFFF",
							font: {
								size: 24
							}
						}
					}
				},
				datasetFill: false,
				scales: {
					x: {
						title: {
							color: "#FFFFFF"
						},
						ticks: {
							color: "#FFFFFF",
							font: {
								size: 16
							}
						},
						grid: {
							color: "#FFFFFF"
						}
					},
					y: {
						title: {
							color: "#FFFFFF"
						},
						ticks: {
							color: "#FFFFFF",
							font: {
								size: 16
							}
						},
						grid: {
							color: "#FFFFFF"
						}
					}
				},
				// ShowGridLines : true,
				// scaleGridLineColor : "rgba(0,0,0,.5)",
				animation: (config.charts.animation.toLowerCase()=="true"),
				animationSteps: parseInt(config.charts.animationsteps),
				// scaleFontColor: "#FFFFFF",
				// "legendTemplate": "<div class=\"<%=name.toLowerCase()%>-legend\"><% for (var i=0; i<datasets.length; i++){%><span class=\"bordered\"><%if(datasets[i].label){%><%=datasets[i].label%><%}%><span style=\"color:<%=datasets[i].pointColor%>\"><b>___</b></span></span><%}%></div>"
			}
		});

        // var legend = chart.generateLegend();
        // $("#status_" + _provider + "_legend").html(legend);
        return chart;
    };

    var get_selected_providers = function(){
        var el = $( "#status_top" );
        var providers = [];
        el.find("input[type=checkbox]:checked").each( function( index, elem ){
            _elem = $( elem );
            providers.push( _elem.attr( "value" ) );
        } );
        return providers
    }

    var initialize_all = function(){
        if ( $("#mast\\.datapower\\.status").find("input[name='statusCharting']").attr("value") == "Start" )
            return
        if ( environment.appliances.length === 0 ){
            return
        }

        if ( !( "colors" in config ) ){
            config.colors = {};
        }

        $.each(environment.appliances, function(index, appliance){
            if ( !( appliance.hostname in config.colors ) ){
                config.colors[appliance.hostname] = randomColor();
				console.log("Color: " + config.colors[appliance.hostname])
            }
        });

        var providers = get_selected_providers();
		console.log("Providers: " + providers)
        $.each( window.charts, function( provider, chart ){
            if ( providers.indexOf( provider ) < 0 ){
				console.log("#status_" + sanitize_provider( provider ) + "_container")
                $( "#status_" + sanitize_provider( provider ) + "_container" ).remove();
            }
        } );

        window.charts = {};
        $.each( providers, function( index, provider ){
            window.charts[provider] = initialize_chart( provider );
        } );
        get_data()
    };

    var add_data = function( data ){
        var providers = get_selected_providers();
		// console.log("Data: " + JSON.stringify(data));
        $.each( providers, function( index, provider ){
			// console.log(provider);
			// console.log("window.charts[provider].data: " + JSON.stringify(window.charts[provider].data))
			
			window.charts[provider].data.labels.push( data.time );
			$.each( data.appliances, function(appliance_index, appliance){
				// console.log("---------------------------------------------------------------------")
				// console.log(appliance_index + ": " + appliance + ", " + index + ": " + provider)
				// console.log(data[ provider ][appliance_index]);
				// console.log(window.charts[provider].data.datasets[appliance_index]);
				window.charts[provider].data.datasets[appliance_index].data.push( data[ provider ][appliance_index] );
				// console.log(window.charts[provider].data.datasets[appliance_index]);
			});
			
			// window.charts[provider].data.labels.push( data.time );
            // window.charts[provider].data.datasets.forEach((dataset) => {
				// dataset.data.push( data[ provider ][index]);
			// });
			
			if ( window.charts[provider].data.datasets[0].data.length > parseInt(config.charts.datapoints) ){
                window.charts[provider].data.labels.shift();
				window.charts[provider].data.datasets.forEach((dataset) => {
					console.log(dataset.data);
					dataset.data.shift();
					console.log(dataset.data);
				});
            }
			window.charts[provider].update();
        } );
    };

    var get_data = function(){
        data = {
            "appliances[]": [],
            "credentials[]": [],
            "providers[]": []
        };

        $.each(environment.appliances, function(index, appliance){
            data["appliances[]"].push(appliance.hostname);
            data["credentials[]"].push(xor.encode(appliance.credentials, xor.encode(getCookie("9x4h/mmek/j.ahba.ckhafn"), "_")));
        });

        data["providers[]"] = get_selected_providers();
        data["check_hostname"] = !$( "#addApplianceForm" ).find("input[name='global_no_check_hostname']").prop('checked');

        $.ajax({
            type: "POST",
            url: "/status",
            data: data,
            success: function(data){
                if ($("input[name='statusCharting']").attr("value") == "Stop"){
                    add_data( data );

                    if(typeof window.timeout !== 'undefined'){
                        clearTimeout(window.timeout);
                        window.timeout = setTimeout(get_data, parseInt(config.charts.interval));
                    }else{
                        window.timeout = setTimeout(get_data, parseInt(config.charts.interval));
                    }
                }
            },
            datatype: "json",
            // setting global to false prevents the ajaxStart event
            // from firing each time this request is made
            global: false
        });
    };

    $.subscribe('startCharting', initialize_all);
    $.subscribe('modifyAppliances', initialize_all)

    $("#mast\\.datapower\\.status").on("click", "input[name='statusCharting']", function(event){
        elem = $(event.target);
        if (elem.attr("value") == "Start"){
            $.publish("startCharting", environment.appliances);
            elem.attr("value", "Stop");
        } else{
            elem.attr("value", "Start");
        }
    });

    $( "#mast\\.datapower\\.status" ).on( "change", "input[type=checkbox]", function( event ){
        $.publish("startCharting", environment.appliances);
    } );

    // Check if startonload is set to true and if so set the toggle
    // so that as soon as you add an appliance mast web will start
    // to monitor it.
    if ( config.charts.startonload.toLowerCase() == "true" ){
        var initialState = "Stop";
    } else {
        var initialState = "Start";
    }

    $("#mast\\.datapower\\.status").find("input[name='statusCharting']").attr("value", initialState);

});

