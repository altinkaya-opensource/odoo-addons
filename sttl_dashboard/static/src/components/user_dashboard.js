/** @odoo-module */

import { registry } from "@web/core/registry"
import { KpiCard } from "./kpi_card/kpi_card"
import { session } from "@web/session";
import { loadJS } from "@web/core/assets"
import { ChartRenderer } from "./chart_renderer/chart_renderer"
import { useService } from "@web/core/utils/hooks";
import { ArrowButton } from './arrow_button/arrow_button'


const { Component, onWillStart, useRef, onMounted,useState } = owl

export class DynamicDashboard extends Component {

    toggleToolbar() {
        this.showToolbar.visible = !this.showToolbar.visible;
    }
     createTable() {
        console.log("Create Table clicked");
    }

    createKpiCard() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Kpi Card Generator',
            res_model: 'kpi.card.generator',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_kpi_unique_id: this.chart_generator_id
            }
        });
    }


    openChartGeneratorForm() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Chart Generator',
            res_model: 'chart.generator',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_dashboard_unique_id: this.chart_generator_id
            }
        });
    }

    openTableGeneratorForm() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Table Generator',
            res_model: 'table.generator',
            views: [[false, 'form']],
            target: 'new',
        });
    }


   async onDeleteChart(count,type,id){
     let text = "Are you sure to delete!\nEither OK or Cancel.";

     if(type == 'chart'){
        Swal.fire({
          title: "Do you want to Delete?",
          showDenyButton: true,
          confirmButtonText: "Delete",
        }).then(async (result) => {
          if (result.isConfirmed) {
             try{
               await this.orm.unlink('chart.generator', [id]);
               var filtered_chart_data = this.charts_data['data'].filter((chart)=>{
                  return chart['count']!== count
               })
               this.charts_data['data'] = filtered_chart_data;
               Swal.fire("Deleted!", "", "success");
             }
             catch(e){
              console.log('error occured',e)
             }

          } else if (result.isDenied) {
            Swal.fire("Changes are not saved", "", "info");
          }
        });
     }
     else{
          Swal.fire({
          title: "Do you want to Delete?",
          showDenyButton: true,
          confirmButtonText: "Delete",
        }).then(async(result) => {
          if (result.isConfirmed) {
           try{
               await this.orm.unlink('kpi.card.generator', [id]);
               var filtered_chart_data = this.charts_data['data'].filter((chart)=>{
                  return chart['count']!== count
               })
               this.charts_data['data'] = filtered_chart_data;
               Swal.fire("Deleted!", "", "success");
             }
             catch(e){
              console.log('error occured',e)
             }
          } else if (result.isDenied) {
            Swal.fire("Changes are not saved", "", "info");
          }
        });
     }

   }

    async getChartsData(){
        try{
         const chartdata = await this.orm.call(
            "chart.generator",
            "get_all_charts_data",
            [1,this.chart_generator_id]
        );
        this.charts_data['data'] = []
        const kpi = await this.getKpiCards();
        let combine = [...chartdata,...kpi]
        let sortedChartData = combine.sort((a, b) => a.dashboard_sequence_number - b.dashboard_sequence_number);
        let count=0;
        for(let i=0;i<combine.length;i++){
          combine[i]['count']=count++
        }
        this.charts_data['data'] = sortedChartData;
        }
        catch(e){
         console.log('error occured')
        }
    }


    async getKpiCards(){
     try{
      const kpicards = await this.orm.call(
            "kpi.card.generator",
            "get_all_kpi_cards",
           [1,this.chart_generator_id]
        );
        this.kpi_cards['data'] = kpicards;
        return kpicards
     }catch(e){
      console.log('Error occured')
     }
    }

   async isAdmin(){
//      base.group_erp_manager
      try{
       this.isadmin = await this.user.hasGroup("base.group_erp_manager");
      }catch(e){

      }
   }


    setup(){
      super.setup();
      this.user_details={}
      this.session_details=session
      this.user = useService("user");
      this.charts_data = useState({data:[]})
      this.kpi_cards = useState({data:[]})
      this.showToolbar = useState({ visible: false });
      this.username = session.name;
      this.orm = useService("orm");
      this.action = useService("action");
      onWillStart(async()=>{
       this.chart_generator_id = this.props.action.params.chart_generator
        await loadJS("https://cdn.jsdelivr.net/npm/sweetalert2@11.14.5/dist/sweetalert2.all.min.js")
        await this.isAdmin();
        await this.getChartsData();

      })
    }
}

DynamicDashboard.template = "owl.UserDashboard"
DynamicDashboard.components = { KpiCard,ChartRenderer,ArrowButton }

registry.category("actions").add("owl.user_dashboard", DynamicDashboard)